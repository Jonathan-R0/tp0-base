import socket
import logging
import signal
import threading

from common.utils import ack_batch_client, receive_bet_batch_from_message, recv_from_server, send_all_bytes, store_bets, handle_finished_notification, handle_winners_query

class Server:
    def __init__(self, port, listen_backlog, expected_agencies, program_normal_exit):
        self.shutdown_requested = False
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        self.program_normal_exit = program_normal_exit
        self.client_sockets = []
        self.client_threads = []
        self.threads_lock = threading.Lock()
        
        # Lottery variables
        self.finished_agencies = set()
        self.lottery_completed = False
        self.lottery_lock = threading.Lock()
        self.lottery_condition = threading.Condition(self.lottery_lock)  # Condition variable for lottery completion
        self.expected_agencies = expected_agencies
        
        # Initialize server socket
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind(('', port))
        self._server_socket.listen(listen_backlog)

    def _signal_handler(self) -> None:
        self.shutdown_requested = True
        self.shutdown()
    
    def should_shutdown(self) -> bool:
        return self.shutdown_requested
    
    def shutdown(self) -> None:
        logging.info('action: shutdown | result: in_progress')
        if self._server_socket: self._server_socket.close()
        logging.info('action: shutdown | result: success')

        logging.info('action: shutdown clients | result: in_progress')
        with self.threads_lock:
            client_sockets_copy = self.client_sockets.copy()
        
        for client_sock in client_sockets_copy:
            try:
                client_sock.close()
            except OSError as e:
                logging.error(f'action: shutdown clients | result: fail | error: {e}')
        logging.info('action: shutdown clients | result: success')

        logging.info('action: wait client threads | result: in_progress')
        with self.threads_lock:
            threads_copy = self.client_threads.copy()
        
        for t in threads_copy:
            if t.is_alive():
                t.join(timeout=5.0)
                if t.is_alive():
                    logging.warning(f'action: wait client threads | result: timeout | thread: {t.name}')
        logging.info('action: wait client threads | result: success')

        self.program_normal_exit()

    def run(self) -> None:
        """
        Server loop that accepts new connections and establishes
        communication with clients. After client communication
        finishes, server starts to accept new connections again
        """

        while not self.should_shutdown():
            try:
                client_sock = self._accept_new_connection()
                
                self._cleanup_finished_threads()
                
                thread = threading.Thread(target=self._handle_client_connection, args=(client_sock,))
                thread.daemon = True
                
                with self.threads_lock:
                    self.client_threads.append(thread)
                
                thread.start()
                
            except Exception as e:
                if self.should_shutdown():
                    break
                logging.error(f'action: accept_connection | result: fail | error: {e}')

    def _cleanup_finished_threads(self) -> None:
        """
        Remove finished threads from the thread list to prevent memory leaks.
        """
        with self.threads_lock:
            self.client_threads = [t for t in self.client_threads if t.is_alive()]

    def _handle_client_connection(self, client_sock) -> None:
        """
        Read message from a specific client socket and handle it accordingly.
        The message can be either a batch of bets, a finished notification,
        or a winners query.
        """
        addr_str = self._get_client_address(client_sock)
        logging.info(f'action: handle_client_connection | result: in_progress | client: {addr_str}')
        
        self._add_client_socket(client_sock)
        
        try:
            self._process_client_messages(client_sock, addr_str)
        except Exception as e:
            logging.error(f'action: handle_client_connection | result: fail | client: {addr_str} | error: {e}')
            ack_batch_client(client_sock, [], False)
        finally:
            self._cleanup_client_connection(client_sock, addr_str)

    def _get_client_address(self, client_sock) -> str:
        """Get client address string for logging."""
        try:
            client_addr = client_sock.getpeername()
            return f"{client_addr[0]}:{client_addr[1]}"
        except:
            return "unknown"

    def _add_client_socket(self, client_sock) -> None:
        """Add client socket to the list of connections."""
        with self.threads_lock:
            if client_sock:
                self.client_sockets.append(client_sock)

    def _process_client_messages(self, client_sock, addr_str: str) -> None:
        """Process messages from clients."""
        message_type, data = self._receive_message(client_sock)
        
        if message_type == "BATCH":
            self._handle_batch_message(client_sock, data, addr_str)
        elif message_type == "FINISHED":
            self._handle_finished_and_winners_flow(client_sock, data, addr_str)
        elif message_type == "QUERY_WINNERS":
            self._handle_winners_query(client_sock, data, addr_str)
        else:
            logging.error(f'action: handle_client_connection | result: fail | client: {addr_str} | error: Unknown message type: {message_type}')
            ack_batch_client(client_sock, [], False)

    def _handle_finished_and_winners_flow(self, client_sock, data: str, addr_str: str) -> None:
        """Handle the two-message chain: FINISHED notification followed by QUERY_WINNERS."""
        # Handle the FINISHED notification
        self._handle_finished_message(client_sock, data, addr_str)
        
        # Wait for and handle the QUERY_WINNERS message on the same connection
        self._wait_and_handle_winners_query(client_sock, addr_str)

    def _wait_and_handle_winners_query(self, client_sock, addr_str: str) -> None:
        """Wait for and handle the QUERY_WINNERS message after FINISHED."""
        try:
            logging.info(f'action: waiting_for_winners_query | result: in_progress | client: {addr_str}')
            winner_message_type, winner_data = self._receive_message(client_sock)
            
            if winner_message_type == "QUERY_WINNERS":
                self._handle_winners_query(client_sock, winner_data, addr_str)
            else:
                logging.error(f'action: handle_client_connection | result: fail | client: {addr_str} | error: Expected QUERY_WINNERS after FINISHED, got: {winner_message_type}')
        except Exception as e:
            logging.error(f'action: handle_winners_query_after_finished | result: fail | client: {addr_str} | error: {e}')

    def _cleanup_client_connection(self, client_sock, addr_str: str) -> None:
        """Clean up client connection resources."""
        try:
            client_sock.close()
            logging.debug(f'action: close_client_connection | result: success | client: {addr_str}')
        except:
            logging.debug(f'action: close_client_connection | result: fail | client: {addr_str}')
        
        with self.threads_lock:
            if client_sock in self.client_sockets:
                self.client_sockets.remove(client_sock)

    def _receive_message(self, client_sock) -> tuple:
        """
        Receive and parse the message from client to determine its type.
        Returns (message_type, data) tuple.
        """
        message = recv_from_server(client_sock)
        
        # Parse message type
        if message.startswith("FINISHED|"):
            return "FINISHED", message
        elif message.startswith("QUERY_WINNERS|"):
            return "QUERY_WINNERS", message
        else:
            return "BATCH", message

    def _handle_batch_message(self, client_sock, message, addr_str) -> None:
        """Handle a batch of bets from a client."""
        try:
            bets = receive_bet_batch_from_message(message)
            logging.info(f'action: apuesta_recibida | result: success | cantidad: {len(bets)}')
            store_bets(bets)
            ack_batch_client(client_sock, bets, True)
            logging.info(f'action: handle_client_connection | result: success | client: {addr_str} | cantidad: {len(bets)}')
        except Exception as e:
            logging.error(f'action: handle_client_connection | result: fail | client: {addr_str} | error: {e}')
            ack_batch_client(client_sock, [], False)

    def _handle_finished_message(self, client_sock, message, addr_str) -> None:
        """Handle a finished notification from a client."""
        try:
            agency_id = handle_finished_notification(client_sock, message)
            with self.lottery_condition:
                self.finished_agencies.add(agency_id)
                logging.info(f'action: agency_finished | result: success | agency: {agency_id} | finished_count: {len(self.finished_agencies)} | checked: {self.finished_agencies}/{self.expected_agencies}')
                
                # Check if all expected agencies have finished
                if len(self.finished_agencies) == self.expected_agencies and not self.lottery_completed:
                    self.lottery_completed = True
                    logging.info('action: sorteo | result: success')
                    self.lottery_condition.notify_all()
                    
        except Exception as e:
            logging.error(f'action: handle_finished_message | result: fail | client: {addr_str} | error: {e}')
            # Send error response for non-batch messages
            try:
                response = f"ERROR|{str(e)}\n"
                send_all_bytes(client_sock, response)
            except Exception as send_error:
                logging.error(f'action: send_error_response | result: fail | client: {addr_str} | error: {send_error}')

    def _handle_winners_query(self, client_sock, message, addr_str) -> None:
        """Handle a winners query from a client."""
        try:
            with self.lottery_condition:
                while not self.lottery_completed:
                    logging.info(f'action: waiting_for_lottery | result: in_progress | client: {addr_str} | status: lottery_not_completed')
                    self.lottery_condition.wait()  # Wait until lottery completes
                
            agency_id = handle_winners_query(client_sock, message)
            logging.info(f'action: winners_query_handled | result: success | client: {addr_str} | agency: {agency_id}')
            
        except Exception as e:
            logging.error(f'action: handle_winners_query | result: fail | client: {addr_str} | error: {e}')
            # Send error response for non-batch messages
            try:
                response = f"ERROR|{str(e)}\n"
                send_all_bytes(client_sock, response)
            except Exception as send_error:
                logging.error(f'action: send_error_response | result: fail | client: {addr_str} | error: {send_error}')



    def _accept_new_connection(self) -> socket.socket:
        """
        Accept new connections

        Function blocks until a connection to a client is made.
        Then connection created is printed and returned
        """
        # Connection arrived
        logging.info('action: accept_connections | result: in_progress')
        c, addr = self._server_socket.accept()
        logging.info(f'action: accept_connections | result: success | ip: {addr[0]}')
        return c

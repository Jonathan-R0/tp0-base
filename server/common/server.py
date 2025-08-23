import socket
import logging
import signal
import threading

from common.utils import ack_batch_client, receive_bet_batch_from_message, store_bets, handle_finished_notification, handle_winners_query


class Server:
    def __init__(self, port, listen_backlog, expected_agencies, program_normal_exit):
        self.shutdown_requested = False
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        self.program_normal_exit = program_normal_exit
        self.client_sockets = []
        self.client_threads = []
        
        # Lottery variables
        self.finished_agencies = set()
        self.lottery_completed = False
        self.lottery_lock = threading.Lock()
        self.expected_agencies = expected_agencies
        
        # Initialize server socket
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.bind(('', port))
        self._server_socket.listen(listen_backlog)

    def _signal_handler(self, _signum, _frame):
        self.shutdown_requested = True
        self.shutdown()
    
    def should_shutdown(self):
        return self.shutdown_requested
    
    def shutdown(self):
        logging.info('action: shutdown | result: in_progress')
        if self._server_socket: self._server_socket.close()
        logging.info('action: shutdown | result: success')

        logging.info('action: shutdown clients | result: in_progress')
        for client_sock in self.client_sockets:
            try:
                client_sock.close()
            except OSError as e:
                logging.error(f'action: shutdown clients | result: fail')
        logging.info('action: shutdown clients | result: success')

        logging.info('action: wait client threads | result: in_progress')
        for t in self.client_threads:
            t.join()
        logging.info('action: wait client threads | result: success')

        self.program_normal_exit()

    def run(self):
        """
        Server loop that accepts new connections and establishes
        communication with clients. After client communication
        finishes, server starts to accept new connections again
        """

        while not self.should_shutdown():
            try:
                client_sock = self.__accept_new_connection()
                self.client_threads.append(threading.Thread(target=self.__handle_client_connection, args=(client_sock,)))
            except:
                if self.should_shutdown():
                    break

    def __handle_client_connection(self, client_sock):
        """
        Read message from a specific client socket and handle it accordingly.
        The message can be either a batch of bets, a finished notification,
        or a winners query.
        """
        try:
            client_addr = client_sock.getpeername()
            addr_str = f"{client_addr[0]}:{client_addr[1]}"
        except:
            addr_str = "unknown"
        
        logging.info(f'action: handle_client_connection | result: in_progress | client: {addr_str}')
        
        if client_sock: self.client_sockets.append(client_sock)
        try:
            message_type, data = self.__receive_message(client_sock)
            
            if message_type == "BATCH":
                self.__handle_batch_message(client_sock, data, addr_str)
            elif message_type == "FINISHED":
                self.__handle_finished_message(client_sock, data, addr_str)
            elif message_type == "QUERY_WINNERS":
                self.__handle_winners_query(client_sock, data, addr_str)
            else:
                logging.error(f'action: handle_client_connection | result: fail | client: {addr_str} | error: Unknown message type: {message_type}')
                ack_batch_client(client_sock, [], False)
                
        except Exception as e:
            logging.error(f'action: handle_client_connection | result: fail | client: {addr_str} | error: {e}')
            ack_batch_client(client_sock, [], False)
        finally:
            try:
                client_sock.close()
                logging.debug(f'action: close_client_connection | result: success | client: {addr_str}')
            except:
                logging.debug(f'action: close_client_connection | result: fail | client: {addr_str}')
            if client_sock in self.client_sockets: 
                self.client_sockets.remove(client_sock)

    def __receive_message(self, client_sock):
        """
        Receive and parse the message from client to determine its type.
        Returns (message_type, data) tuple.
        """
        size_bytes = client_sock.recv(2)
        if len(size_bytes) != 2:
            raise ConnectionError("Failed to read message size")
        
        size = int.from_bytes(size_bytes, byteorder='big')
        
        data = b""
        while len(data) < size:
            remaining = size - len(data)
            packet = client_sock.recv(remaining)
            if not packet:
                raise ConnectionError("Connection closed before reading all data")
            data += packet
        
        message = data.decode('utf-8').strip()
        
        # Parse message type
        if message.startswith("FINISHED|"):
            return "FINISHED", message
        elif message.startswith("QUERY_WINNERS|"):
            return "QUERY_WINNERS", message
        else:
            return "BATCH", message

    def __handle_batch_message(self, client_sock, message, addr_str):
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

    def __handle_finished_message(self, client_sock, message, addr_str):
        """Handle a finished notification from a client."""
        try:
            agency_id = handle_finished_notification(client_sock, message)
            with self.lottery_lock:
                self.finished_agencies.add(agency_id)
                logging.info(f'action: agency_finished | result: success | agency: {agency_id} | finished_count: {len(self.finished_agencies)} | checked: {self.finished_agencies}/{self.expected_agencies}')
                
                # Check if all expected agencies have finished
                if len(self.finished_agencies) == self.expected_agencies and not self.lottery_completed:
                    self.lottery_completed = True
                    logging.info('action: sorteo | result: success')
                    
        except Exception as e:
            logging.error(f'action: handle_finished_message | result: fail | client: {addr_str} | error: {e}')
            # Send error response for non-batch messages
            try:
                response = f"ERROR|{str(e)}\n"
                client_sock.send(response.encode('utf-8'))
            except:
                pass

    def __handle_winners_query(self, client_sock, message, addr_str):
        """Handle a winners query from a client."""
        try:
            if not self.lottery_completed:
                # Send error response for non-batch messages
                try:
                    response = f"ERROR|Lottery not yet completed\n"
                    client_sock.send(response.encode('utf-8'))
                except:
                    pass
                return
                
            agency_id = handle_winners_query(client_sock, message)
            logging.info(f'action: winners_query_handled | result: success | client: {addr_str} | agency: {agency_id}')
            
        except Exception as e:
            logging.error(f'action: handle_winners_query | result: fail | client: {addr_str} | error: {e}')
            # Send error response for non-batch messages
            try:
                response = f"ERROR|{str(e)}\n"
                client_sock.send(response.encode('utf-8'))
            except:
                pass



    def __accept_new_connection(self):
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

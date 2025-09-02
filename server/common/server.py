import socket
import logging
import signal

from common.utils import ack_client, receive_bet, store_bets


class Server:
    def __init__(self, port, listen_backlog, program_normal_exit):
        self.shutdown_requested = False
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        self.program_normal_exit = program_normal_exit
        self.client_sockets = []
        # Initialize server socket
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.bind(('', port))
        self._server_socket.listen(listen_backlog)

    def _signal_handler(self, _signum, _frame) -> None:
        logging.info(f'action: signal_handler | result: in_progress | signal: {_signum} | frame: {_frame}')
        self.shutdown_requested = True
        self.shutdown()
    
    def should_shutdown(self) -> bool:
        return self.shutdown_requested
    
    def shutdown(self) -> None:
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

        self.program_normal_exit()

    def run(self) -> None:
        """
        Dummy Server loop

        Server that accept a new connections and establishes a
        communication with a client. After client with communucation
        finishes, servers starts to accept new connections again
        """

        while not self.should_shutdown():
            try:
                client_sock = self.__accept_new_connection()
                self.__handle_client_connection(client_sock)
            except:
                if self.should_shutdown():
                    break

    def __handle_client_connection(self, client_sock) -> None:
        """
        Read message from a specific client socket and closes the socket

        If a problem arises in the communication with the client, the
        client socket will also be closed
        """
        try:
            client_addr = client_sock.getpeername()
            addr_str = f"{client_addr[0]}:{client_addr[1]}"
        except:
            addr_str = "unknown"
        
        logging.info(f'action: handle_client_connection | result: in_progress | client: {addr_str}')
        
        if client_sock: self.client_sockets.append(client_sock)
        try:
            bet = receive_bet(client_sock)
            logging.info(f'action: apuesta_almacenada | result: in_progress | client: {addr_str} | dni: {bet.document} | numero: {bet.number}')
            store_bets([bet])
            logging.info(f'action: apuesta_almacenada | result: success | client: {addr_str} | dni: {bet.document} | numero: {bet.number}')
            ack_client(client_sock, bet)
            logging.info(f'action: handle_client_connection | result: success | client: {addr_str} | dni: {bet.document} | numero: {bet.number}')
        except (OSError, ValueError, ConnectionError) as e:
            logging.error(f'action: handle_client_connection | result: fail | client: {addr_str} | error: {e}')
        except Exception as e:
            logging.error(f'action: handle_client_connection | result: fail | client: {addr_str} | unexpected_error: {e}')
        finally:
            try:
                client_sock.close()
                logging.debug(f'action: close_client_connection | result: success | client: {addr_str}')
            except:
                logging.debug(f'action: close_client_connection | result: fail | client: {addr_str}')
            if client_sock in self.client_sockets: 
                self.client_sockets.remove(client_sock)

    def __accept_new_connection(self) -> socket.socket:
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

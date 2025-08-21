import socket
import logging
import signal


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

        self.program_normal_exit()

    def run(self):
        """
        Dummy Server loop

        Server that accept a new connections and establishes a
        communication with a client. After client with communucation
        finishes, servers starts to accept new connections again
        """

        # TODO: Modify this program to handle signal to graceful shutdown
        # the server
        while not self.should_shutdown():
            try:
                client_sock = self.__accept_new_connection()
                self.__handle_client_connection(client_sock)
            except:
                if self.should_shutdown():
                    break

    def __handle_client_connection(self, client_sock):
        """
        Read message from a specific client socket and closes the socket

        If a problem arises in the communication with the client, the
        client socket will also be closed
        """
        if client_sock: self.client_sockets.append(client_sock)
        try:
            # TODO: Modify the receive to avoid short-reads
            msg = client_sock.recv(1024).rstrip().decode('utf-8')
            addr = client_sock.getpeername()
            logging.info(f'action: receive_message | result: success | ip: {addr[0]} | msg: {msg}')
            # TODO: Modify the send to avoid short-writes
            client_sock.send("{}\n".format(msg).encode('utf-8'))
        except OSError as e:
            logging.error("action: receive_message | result: fail | error: {e}")
        finally:
            client_sock.close()
            if client_sock: self.client_sockets.remove(client_sock)

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

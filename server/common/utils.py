import csv
import datetime
import time


""" Bets storage location. """
STORAGE_FILEPATH = "./bets.csv"
""" Simulated winner number in the lottery contest. """
LOTTERY_WINNER_NUMBER = 7574


""" A lottery bet registry. """
class Bet:
    def __init__(self, agency: str, first_name: str, last_name: str, document: str, birthdate: str, number: str):
        """
        agency must be passed with integer format.
        birthdate must be passed with format: 'YYYY-MM-DD'.
        number must be passed with integer format.
        """
        self.agency = int(agency)
        self.first_name = first_name
        self.last_name = last_name
        self.document = document
        self.birthdate = datetime.date.fromisoformat(birthdate)
        self.number = int(number)

""" Checks whether a bet won the prize or not. """
def has_won(bet: Bet) -> bool:
    return bet.number == LOTTERY_WINNER_NUMBER

"""
Persist the information of each bet in the STORAGE_FILEPATH file.
Not thread-safe/process-safe.
"""
def store_bets(bets: list[Bet]) -> None:
    with open(STORAGE_FILEPATH, 'a+') as file:
        writer = csv.writer(file, quoting=csv.QUOTE_MINIMAL)
        for bet in bets:
            writer.writerow([bet.agency, bet.first_name, bet.last_name,
                             bet.document, bet.birthdate, bet.number])

"""
Loads the information all the bets in the STORAGE_FILEPATH file.
Not thread-safe/process-safe.
"""
def load_bets() -> list[Bet]:
    with open(STORAGE_FILEPATH, 'r') as file:
        reader = csv.reader(file, quoting=csv.QUOTE_MINIMAL)
        for row in reader:
            yield Bet(row[0], row[1], row[2], row[3], row[4], row[5])

"""
Receives a bet from a client socket.
"""
def receive_bet(client_sock) -> Bet:
    import logging
    
    try:
        client_addr = client_sock.getpeername()
        addr_str = f"{client_addr[0]}:{client_addr[1]}"
    except:
        addr_str = "unknown"
    
    logging.info(f'action: receive_bet | result: in_progress | client: {addr_str}')
    
    size_bytes = client_sock.recv(2)
    if len(size_bytes) != 2:
        logging.error(f'action: receive_bet | result: fail | client: {addr_str} | error: Failed to read message size, got {len(size_bytes)} bytes')
        raise ConnectionError("Failed to read message size")
    
    size = int.from_bytes(size_bytes, byteorder='big')
    logging.debug(f'action: receive_bet | result: in_progress | client: {addr_str} | message_size: {size} bytes')
    
    data = b""
    while len(data) < size:
        remaining = size - len(data)
        packet = client_sock.recv(remaining)
        if not packet:
            logging.error(f'action: receive_bet | result: fail | client: {addr_str} | error: Connection closed before reading all data, got {len(data)}/{size} bytes')
            raise ConnectionError("Connection closed before reading all data")
        data += packet
        logging.debug(f'action: receive_bet | result: in_progress | client: {addr_str} | received: {len(data)}/{size} bytes')
    
    bet_data = data.decode('utf-8').strip().split('|')
    logging.debug(f'action: receive_bet | result: in_progress | client: {addr_str} | fields_count: {len(bet_data)}')
    
    if len(bet_data) != 6:
        logging.error(f'action: receive_bet | result: fail | client: {addr_str} | error: Invalid bet data format: expected 6 fields, got {len(bet_data)}')
        raise ValueError(f"Invalid bet data format: expected 6 fields, got {len(bet_data)}")
    
    logging.debug(f'action: receive_bet | result: in_progress | client: {addr_str} | parsing_fields: agency="{bet_data[0]}" name="{bet_data[1]}" lastname="{bet_data[2]}" document="{bet_data[3]}" birthdate="{bet_data[4]}" number="{bet_data[5]}"')
    
    try:
        bet = Bet(*bet_data)
        logging.info(f'action: receive_bet | result: success | client: {addr_str} | agency: {bet.agency} | dni: {bet.document} | number: {bet.number}')
        return bet
    except Exception as e:
        logging.error(f'action: receive_bet | result: fail | client: {addr_str} | error: Failed to create Bet object: {e}')
        raise
 
"""
Acknowledges a bet by echoing it back to the client.
"""
def ack_client(client_sock, bet) -> None:
    import logging
    
    try:
        client_addr = client_sock.getpeername()
        addr_str = f"{client_addr[0]}:{client_addr[1]}"
    except:
        addr_str = "unknown"
    
    logging.info(f'action: ack_client | result: in_progress | client: {addr_str} | dni: {bet.document} | number: {bet.number}')
    
    response = f"{bet.agency}|{bet.first_name}|{bet.last_name}|{bet.document}|{bet.birthdate}|{bet.number}\n"
    logging.debug(f'action: ack_client | result: in_progress | client: {addr_str} | response_size: {len(response.encode("utf-8"))} bytes')
    
    try:
        bytes_sent = send_all_bytes(client_sock, response)
        logging.debug(f'action: ack_client | result: in_progress | client: {addr_str} | bytes_sent: {bytes_sent}/{len(response.encode("utf-8"))}')
        logging.info(f'action: ack_client | result: success | client: {addr_str} | dni: {bet.document} | number: {bet.number}')
    except Exception as e:
        logging.error(f'action: ack_client | result: fail | client: {addr_str} | dni: {bet.document} | number: {bet.number} | error: {e}')

def send_all_bytes(sock, data) -> int:
    """
    Send all bytes through the socket, handling short sends.
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    total_sent = 0
    while total_sent < len(data):
        try:
            sent = sock.send(data[total_sent:])
            if sent == 0:
                raise ConnectionError("Socket connection broke")
            total_sent += sent
        except Exception as e:
            raise ConnectionError(f"Failed to send data: {e}")
    return total_sent
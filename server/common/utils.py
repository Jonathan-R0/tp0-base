import csv
import datetime
import logging

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
Receives a batch of bets from a client socket.
"""
def receive_bet_batch(client_sock) -> list[Bet]:
    addr_str = _get_client_address(client_sock)
    logging.info(f'action: receive_bet_batch | result: in_progress | client: {addr_str}')
    
    message = _read_full_message(client_sock, addr_str)
    bet_lines = _parse_batch_message(message, addr_str)
    
    bets = _process_bet_lines(bet_lines, addr_str)
    
    logging.info(f'action: receive_bet_batch | result: success | client: {addr_str} | bets_count: {len(bets)}')
    return bets

def _get_client_address(client_sock) -> str:
    """Get client address string for logging."""
    try:
        client_addr = client_sock.getpeername()
        return f"{client_addr[0]}:{client_addr[1]}"
    except:
        return "unknown"

def _read_full_message(client_sock, addr_str: str) -> str:
    """Read the complete message from client socket."""
    size_bytes = client_sock.recv(2)
    if len(size_bytes) != 2:
        logging.error(f'action: receive_bet_batch | result: fail | client: {addr_str} | error: Failed to read message size')
        raise ConnectionError("Failed to read message size")
    
    size = int.from_bytes(size_bytes, byteorder='big')
    logging.debug(f'action: receive_bet_batch | result: in_progress | client: {addr_str} | message_size: {size} bytes')
    
    data = b""
    while len(data) < size:
        remaining = size - len(data)
        packet = client_sock.recv(remaining)
        if not packet:
            logging.error(f'action: receive_bet_batch | result: fail | client: {addr_str} | error: Connection closed unexpectedly')
            raise ConnectionError("Connection closed before reading all data")
        data += packet
    
    return data.decode('utf-8').strip()

def _parse_batch_message(message: str, addr_str: str) -> list[str]:
    """Parse batch message and return batch count and bet lines."""
    lines = message.split('\n')
    if not lines:
        logging.error(f'action: receive_bet_batch | result: fail | client: {addr_str} | error: Empty batch message')
        raise ValueError("Empty batch message")
    
    try:
        batch_count = int(lines[0].strip())
    except ValueError:
        logging.error(f'action: receive_bet_batch | result: fail | client: {addr_str} | error: Invalid batch count: {lines[0]}')
        raise ValueError(f"Invalid batch count: {lines[0]}")
    
    bet_lines = lines[1:]
    if len(bet_lines) != batch_count:
        logging.error(f'action: receive_bet_batch | result: fail | client: {addr_str} | error: Expected {batch_count} bets, got {len(bet_lines)}')
        raise ValueError(f"Batch count mismatch: expected {batch_count} bets, got {len(bet_lines)}")
    
    logging.debug(f'action: receive_bet_batch | result: in_progress | client: {addr_str} | batch_count: {batch_count}')
    return bet_lines

def _process_bet_lines(bet_lines: list[str], addr_str: str) -> list[Bet]:
    """Process bet lines and create Bet objects."""
    bets = []
    for i, bet_line in enumerate(bet_lines):
        if not bet_line.strip():
            continue
            
        bet_data = bet_line.strip().split('|')
        if len(bet_data) != 6:
            logging.error(f'action: receive_bet_batch | result: fail | client: {addr_str} | error: Invalid bet data at line {i+1}')
            raise ValueError(f"Invalid bet data format at line {i+1}: expected 6 fields, got {len(bet_data)}")
        
        logging.debug(f'action: receive_bet_batch | result: in_progress | client: {addr_str} | line {i+1}: agency="{bet_data[0]}" name="{bet_data[1]}" lastname="{bet_data[2]}" document="{bet_data[3]}" birthdate="{bet_data[4]}" number="{bet_data[5]}"')
        
        try:
            bet = Bet(*bet_data)
            bets.append(bet)
        except Exception as e:
            logging.error(f'action: receive_bet_batch | result: fail | client: {addr_str} | error: Failed to create Bet object at line {i+1}: {e}')
            raise
    
    return bets

"""
Acknowledges a batch of bets by sending success/failure response to the client.
"""
def ack_batch_client(client_sock, bets: list[Bet], success: bool) -> None:
    try:
        client_addr = client_sock.getpeername()
        addr_str = f"{client_addr[0]}:{client_addr[1]}"
    except:
        addr_str = "unknown"
    
    status = "SUCCESS" if success else "FAIL"
    quantity = len(bets)
    
    logging.info(f'action: ack_batch_client | result: in_progress | client: {addr_str} | status: {status} | bets_count: {quantity}')
    
    response = f"{status}|{quantity}\n"
    logging.debug(f'action: ack_batch_client | result: in_progress | client: {addr_str} | response_size: {len(response.encode("utf-8"))} bytes')
    
    try:
        bytes_sent = send_all_bytes(client_sock, response)
        logging.debug(f'action: ack_batch_client | result: in_progress | client: {addr_str} | bytes_sent: {bytes_sent}/{len(response.encode("utf-8"))}')
        logging.info(f'action: ack_batch_client | result: success | client: {addr_str} | status: {status} | bets_count: {quantity}')
    except Exception as e:
        logging.error(f'action: ack_batch_client | result: fail | client: {addr_str} | status: {status} | bets_count: {quantity} | error: {e}')

def send_all_bytes(sock, data):
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

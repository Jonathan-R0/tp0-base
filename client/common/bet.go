package common

import (
	"bufio"
	"encoding/binary"
	"encoding/csv"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
)

type Bet struct {
	Agency string
	Name string
	Lastname string
	Document int
	Birthdate string
	Number int
}

type BetBatch struct {
	Bets []Bet
}

func NewBetBatch(bets []Bet) *BetBatch {
	return &BetBatch{Bets: bets}
}

type BatchReader struct {
	file        *os.File
	csvReader   *csv.Reader
	agencyID    string
	maxBatchSize int
	eof         bool
	pendingBet  *Bet
}

func NewBatchReader(filename string, agencyID string, maxBatchSize int) (*BatchReader, error) {
	file, err := os.Open(filename)
	if err != nil {
		return nil, fmt.Errorf("failed to open CSV file: %v", err)
	}

	reader := csv.NewReader(file)
	
	return &BatchReader{
		file:        file,
		csvReader:   reader,
		agencyID:    agencyID,
		maxBatchSize: maxBatchSize,
		eof:         false,
		pendingBet:  nil,
	}, nil
}

func (br *BatchReader) ReadNextBatch() (*BetBatch, error) {
	if br.eof {
		return nil, nil
	}

	const maxBytesPerBatch = 1024 * 8
	var currentBatch []Bet
	currentBatchBytes := 0

	for {
		var bet Bet
		
		if br.pendingBet != nil {
			// Check if there is a pending bet to be sent
			bet = *br.pendingBet
			br.pendingBet = nil
		} else {
			record, err := br.csvReader.Read()
			if err != nil {
				if err.Error() == "EOF" {
					br.eof = true
					break
				}
				return nil, fmt.Errorf("failed to read CSV record: %v", err)
			}

			if len(record) != 5 {
				return nil, fmt.Errorf("invalid record: expected 5 fields, got %d", len(record))
			}

			document, err := strconv.Atoi(strings.TrimSpace(record[2]))
			if err != nil {
				return nil, fmt.Errorf("invalid document: %v", err)
			}

			number, err := strconv.Atoi(strings.TrimSpace(record[4]))
			if err != nil {
				return nil, fmt.Errorf("invalid number: %v", err)
			}

			bet = Bet{
				Agency:    br.agencyID,
				Name:      strings.TrimSpace(record[0]),
				Lastname:  strings.TrimSpace(record[1]),
				Document:  document,
				Birthdate: strings.TrimSpace(record[3]),
				Number:    number,
			}
		}

		betLine := fmt.Sprintf("%s|%s|%s|%d|%s|%d\n", bet.Agency, bet.Name, bet.Lastname, bet.Document, bet.Birthdate, bet.Number)
		betSize := len(betLine)

		if len(currentBatch) > 0 && (currentBatchBytes + betSize > maxBytesPerBatch) {
			br.pendingBet = &bet
			break
		}

		currentBatch = append(currentBatch, bet)
		currentBatchBytes += betSize

		if br.maxBatchSize > 0 && len(currentBatch) >= br.maxBatchSize {
			break
		}
	}

	if len(currentBatch) == 0 {
		return nil, nil
	}

	return NewBetBatch(currentBatch), nil
}

func (batch *BetBatch) SendBatchToServer(conn net.Conn) error {
	log.Infof("action: send_batch | result: in_progress | bets_count: %d", len(batch.Bets))
	
	var batchMessage strings.Builder
	batchMessage.WriteString(fmt.Sprintf("%d\n", len(batch.Bets)))
	
	for _, bet := range batch.Bets {
		betMessage := fmt.Sprintf("%s|%s|%s|%d|%s|%d\n", 
			bet.Agency, bet.Name, bet.Lastname, bet.Document, bet.Birthdate, bet.Number)
		batchMessage.WriteString(betMessage)
	}
	
	message := batchMessage.String()
	log.Debugf("action: send_batch | result: in_progress | bets_count: %d | message_size: %d bytes", 
		len(batch.Bets), len(message))
	
	if err := SendMessageWithHeader(conn, message); err != nil {
		log.Errorf("action: send_batch | result: fail | bets_count: %d | error: %v", 
			len(batch.Bets), err)
		return err
	}

	log.Infof("action: send_batch | result: success | bets_count: %d", len(batch.Bets))
	return nil
}

func (batch *BetBatch) ReceiveBatchResponse(conn net.Conn) error {
	log.Infof("action: receive_batch_response | result: in_progress | bets_count: %d", len(batch.Bets))
	
	msg, err := bufio.NewReader(conn).ReadString('\n')
	if err != nil {
		log.Errorf("action: receive_batch_response | result: fail | bets_count: %d | error: %v", len(batch.Bets), err)
		return err
	}
	
	log.Debugf("action: receive_batch_response | result: in_progress | bets_count: %d | message_size: %d bytes", 
		len(batch.Bets), len(msg))
	
	data := strings.Split(strings.TrimSpace(msg), "|")
	if len(data) != 2 {
		log.Errorf("action: receive_batch_response | result: fail | bets_count: %d | error: expected 2 fields, got %d", 
			len(batch.Bets), len(data))
		return fmt.Errorf("invalid response format")
	}

	status := data[0]
	quantityStr := data[1]
	
	quantity, err := strconv.Atoi(quantityStr)
	if err != nil {
		log.Errorf("action: receive_batch_response | result: fail | bets_count: %d | error: invalid quantity: %v", 
			len(batch.Bets), err)
		return err
	}

	if status == "SUCCESS" {
		log.Infof("action: apuesta_enviada | result: success | bets_count: %d | processed: %d", 
			len(batch.Bets), quantity)
	} else {
		log.Errorf("action: apuesta_enviada | result: fail | bets_count: %d | processed: %d", 
			len(batch.Bets), quantity)
		return fmt.Errorf("batch processing failed")
	}
	
	return nil
}


// SendMessageWithHeader sends a message with a 2-byte size header
func SendMessageWithHeader(conn net.Conn, message string) error {
	messageBytes := []byte(message)
	
	sizeBuffer := make([]byte, 2)
	binary.BigEndian.PutUint16(sizeBuffer, uint16(len(messageBytes)))
	
	if err := WriteAllBytes(conn, sizeBuffer); err != nil {
		return fmt.Errorf("failed to send size header: %v", err)
	}
	
	if err := WriteAllBytes(conn, messageBytes); err != nil {
		return fmt.Errorf("failed to send message: %v", err)
	}
	
	return nil
}

// WriteAllBytes writes all bytes to the connection, handling partial writes
func WriteAllBytes(conn net.Conn, data []byte) error {
	totalWritten := 0
	for totalWritten < len(data) {
		n, err := conn.Write(data[totalWritten:])
		if err != nil {
			return fmt.Errorf("failed to write data: %v", err)
		}
		totalWritten += n
	}
	return nil
}

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

func ReadBetsFromCSV(filename string, agencyID string) ([]Bet, error) {
	file, err := os.Open(filename)
	if err != nil {
		return nil, fmt.Errorf("failed to open CSV file: %v", err)
	}
	defer file.Close()

	reader := csv.NewReader(file)
	records, err := reader.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("failed to read CSV file: %v", err)
	}

	var bets []Bet
	for i, record := range records {
		if len(record) != 5 {
			return nil, fmt.Errorf("invalid record at line %d: expected 5 fields, got %d", i+1, len(record))
		}

		document, err := strconv.Atoi(strings.TrimSpace(record[2]))
		if err != nil {
			return nil, fmt.Errorf("invalid document at line %d: %v", i+1, err)
		}

		number, err := strconv.Atoi(strings.TrimSpace(record[4]))
		if err != nil {
			return nil, fmt.Errorf("invalid number at line %d: %v", i+1, err)
		}

		bet := Bet{
			Agency:   agencyID,
			Name:     strings.TrimSpace(record[0]),
			Lastname: strings.TrimSpace(record[1]),
			Document: document,
			Birthdate: strings.TrimSpace(record[3]),
			Number:   number,
		}
		bets = append(bets, bet)
	}

	return bets, nil
}

func CreateBatches(bets []Bet, maxBatchSize int) []*BetBatch {
	const maxBytesPerBatch = 1024 * 8
	var batches []*BetBatch
	var currentBatch []Bet
	currentBatchBytes := 0

	for _, bet := range bets {
		betLine := fmt.Sprintf("%s|%s|%s|%d|%s|%d\n", bet.Agency, bet.Name, bet.Lastname, bet.Document, bet.Birthdate, bet.Number)
		betSize := len(betLine)

		if len(currentBatch) > 0 && (currentBatchBytes + betSize > maxBytesPerBatch) {
			batches = append(batches, NewBetBatch(currentBatch))
			currentBatch = nil
			currentBatchBytes = 0
		}

		currentBatch = append(currentBatch, bet)
		currentBatchBytes += betSize

		if maxBatchSize > 0 && len(currentBatch) >= maxBatchSize {
			batches = append(batches, NewBetBatch(currentBatch))
			currentBatch = nil
			currentBatchBytes = 0
		}
	}

	if len(currentBatch) > 0 {
		batches = append(batches, NewBetBatch(currentBatch))
	}

	return batches
}

func DoParseToNumber(s string) int {
	number, _ := strconv.Atoi(strings.TrimSpace(s))
	return number
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
	
	messageBytes := []byte(message)
	sizeBuffer := make([]byte, 2)

	binary.BigEndian.PutUint16(sizeBuffer, uint16(len(messageBytes)))
	log.Debugf("action: send_batch | result: in_progress | bets_count: %d | sending_size_header: %d bytes", 
		len(batch.Bets), len(messageBytes))

	if err := batch.WriteAllBytes(conn, sizeBuffer); err != nil {
		log.Errorf("action: send_batch | result: fail | bets_count: %d | error: failed to send size header: %v", 
			len(batch.Bets), err)
		return err
	}

	if err := batch.WriteAllBytes(conn, messageBytes); err != nil {
		log.Errorf("action: send_batch | result: fail | bets_count: %d | error: failed to send message: %v", 
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

func (batch *BetBatch) WriteAllBytes(conn net.Conn, data []byte) error {
	log.Debugf("action: write_batch_bytes | result: in_progress | bets_count: %d | total_bytes: %d", 
		len(batch.Bets), len(data))
	
	totalWritten := 0
	for totalWritten < len(data) {
		n, err := conn.Write(data[totalWritten:])
		if err != nil {
			log.Errorf("action: write_batch_bytes | result: fail | bets_count: %d | error: %v", 
				len(batch.Bets), err)
			return err
		}
		totalWritten += n
		log.Debugf("action: write_batch_bytes | result: in_progress | bets_count: %d | written: %d/%d bytes", 
			len(batch.Bets), totalWritten, len(data))
	}
	
	log.Debugf("action: write_batch_bytes | result: success | bets_count: %d | total_written: %d bytes", 
		len(batch.Bets), totalWritten)
	return nil
}

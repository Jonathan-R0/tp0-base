package common

import (
	"bufio"
	"encoding/binary"
	"fmt"
	"net"
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

func DoParseToNumber(s string) int {
	number, _ := strconv.Atoi(strings.TrimSpace(s))
	return number
}

func (b *Bet) ReceiveBytesAndAssertAllDataMatches(conn net.Conn) {
	log.Infof("action: receive_response | result: in_progress | dni: %d | numero: %d", b.Document, b.Number)
	
	msg, err := bufio.NewReader(conn).ReadString('\n')
	if err != nil {
		log.Errorf("action: receive_response | result: fail | dni: %d | numero: %d | error: %v", b.Document, b.Number, err)
		return
	}
	
	log.Debugf("action: receive_response | result: in_progress | dni: %d | numero: %d | message_size: %d bytes", 
		b.Document, b.Number, len(msg))
	
	data := strings.Split(strings.TrimSpace(msg), "|")
	if len(data) != 6 {
		log.Errorf("action: receive_response | result: fail | dni: %d | numero: %d | error: expected 6 fields, got %d", 
			b.Document, b.Number, len(data))
		return
	}

	log.Debugf("action: receive_response | result: in_progress | dni: %d | numero: %d | parsed_fields: %v", 
		b.Document, b.Number, data)

	receivedDocumentInt := DoParseToNumber(data[3])
	receivedNumberInt := DoParseToNumber(data[5])
	if receivedDocumentInt != b.Document || receivedNumberInt != b.Number ||
		data[0] != b.Agency || data[1] != b.Name || data[2] != b.Lastname || data[4] != b.Birthdate {
		log.Errorf("action: apuesta_enviada | result: fail | dni: %d | numero: %d | error: response validation failed", 
			b.Document, b.Number)
	} else {
		log.Infof("action: apuesta_enviada | result: success | dni: %d | numero: %d", b.Document, b.Number)
	}
}

func (b *Bet) WriteAllBytes(conn net.Conn, data []byte) error {
	log.Debugf("action: write_bytes | result: in_progress | dni: %d | numero: %d | total_bytes: %d", 
		b.Document, b.Number, len(data))
	
	totalWritten := 0
	for totalWritten < len(data) {
		n, err := conn.Write(data[totalWritten:])
		if err != nil {
			log.Errorf("action: write_bytes | result: fail | dni: %v | numero: %v | error: %v", 
				b.Document, b.Number, err)
			return err
		}
		totalWritten += n
		log.Debugf("action: write_bytes | result: in_progress | dni: %d | numero: %d | written: %d/%d bytes", 
			b.Document, b.Number, totalWritten, len(data))
	}
	
	log.Debugf("action: write_bytes | result: success | dni: %d | numero: %d | total_written: %d bytes", 
		b.Document, b.Number, totalWritten)
	return nil
}

func (b *Bet) SendBetToServer(conn net.Conn) error {
	log.Infof("action: send_bet | result: in_progress | dni: %d | numero: %d", b.Document, b.Number)
	
	message := fmt.Sprintf("%s|%s|%s|%d|%s|%d\n", b.Agency, b.Name, b.Lastname, b.Document, b.Birthdate, b.Number)
	log.Debugf("action: send_bet | result: in_progress | dni: %d | numero: %d | message_size: %d bytes", 
		b.Document, b.Number, len(message))
	
	messageBytes := []byte(message)
	sizeBuffer := make([]byte, 2)

	binary.BigEndian.PutUint16(sizeBuffer, uint16(len(messageBytes)))
	log.Debugf("action: send_bet | result: in_progress | dni: %d | numero: %d | sending_size_header: %d bytes", 
		b.Document, b.Number, len(messageBytes))

	if err := b.WriteAllBytes(conn, sizeBuffer); err != nil {
		log.Errorf("action: send_bet | result: fail | dni: %d | numero: %d | error: failed to send size header: %v", 
			b.Document, b.Number, err)
		return err
	}

	if err := b.WriteAllBytes(conn, messageBytes); err != nil {
		log.Errorf("action: send_bet | result: fail | dni: %d | numero: %d | error: failed to send message: %v", 
			b.Document, b.Number, err)
		return err
	}

	log.Infof("action: send_bet | result: success | dni: %d | numero: %d", b.Document, b.Number)
	return nil
}
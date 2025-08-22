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
	msg, err := bufio.NewReader(conn).ReadString('\n')
	if err != nil {
		log.Errorf("action: receive_bytes | result: fail | error: %v", err)
		return
	}
	data := strings.Split(strings.TrimSpace(msg), "|")
	if len(data) != 6 {
		err := fmt.Errorf("action: receive_bytes | result: fail | error: expected 6 fields, got %d", len(data))
		log.Error(err)
		return
	}

	receivedDocumentInt := DoParseToNumber(data[3])
	receivedNumberInt := DoParseToNumber(data[5])
	if receivedDocumentInt != b.Document || receivedNumberInt != b.Number ||
		data[0] != b.Agency || data[1] != b.Name || data[2] != b.Lastname || data[4] != b.Birthdate {
		log.Infof("action: apuesta_enviada | result: fail | expected: %s|%s|%s|%d|%s|%d | received: %s",)
	} else {
		log.Infof("action: apuesta_enviada | result: success | dni: %d | numero: %d", b.Document, b.Number)
	}
}

func (b *Bet) WriteAllBytes(conn net.Conn, data []byte) error {
	totalWritten := 0
	for totalWritten < len(data) {
		n, err := conn.Write(data[totalWritten:])
		if err != nil {
			log.Errorf("action: apuesta_enviada | result: fail | dni: %v | numero: %v | error: %v", b.Document, b.Number, err)
			return err
		}
		totalWritten += n
	}
	return nil
}

func (b *Bet) SendBetToServer(conn net.Conn) error {
	message := fmt.Sprintf("%s|%s|%s|%d|%s|%d\n", b.Agency, b.Name, b.Lastname, b.Document, b.Birthdate, b.Number)
	
	messageBytes := []byte(message)
	sizeBuffer := make([]byte, 2)

	binary.BigEndian.PutUint16(sizeBuffer, uint16(len(messageBytes)))

	if err := b.WriteAllBytes(conn, sizeBuffer); err != nil {
		return err
	}

	if err := b.WriteAllBytes(conn, messageBytes); err != nil {
		return err
	}

	return nil
}
package common

import (
	"bufio"
	"fmt"
	"net"
	"os"
	"strings"
	"time"

	"github.com/op/go-logging"
)

var log = logging.MustGetLogger("log")

// ClientConfig Configuration used by the client
type ClientConfig struct {
	ID            string
	ServerAddress string
	LoopAmount    int
	LoopPeriod    time.Duration
	MaxBatchAmount int
}

// Client Entity that encapsulates how
type Client struct {
	config ClientConfig
	conn   net.Conn
	bets   []Bet
}

// NewClient Initializes a new client receiving the configuration
// as a parameter
func NewClient(config ClientConfig, bets []Bet) *Client {
	client := &Client{
		config: config,
		bets:   bets,
	}
	return client
}

// CreateClientSocket Initializes client socket. In case of
// failure, error is printed in stdout/stderr and exit 1
// is returned
func (c *Client) createClientSocket() error {
	conn, err := net.Dial("tcp", c.config.ServerAddress)
	if err != nil {
		log.Criticalf(
			"action: connect | result: fail | client_id: %v | error: %v",
			c.config.ID,
			err,
		)
	}
	c.conn = conn
	return nil
}

// StartClientLoop Send batches of bets to the server
func (c *Client) StartClientLoop(sigChannel chan os.Signal) {
	log.Infof("action: start_client_loop | result: in_progress | client_id: %v | total_bets: %d | max_batch_size: %d", 
		c.config.ID, len(c.bets), c.config.MaxBatchAmount)
	
	batches := CreateBatches(c.bets, c.config.MaxBatchAmount)
	log.Infof("action: batches_created | result: success | client_id: %v | total_batches: %d", 
		c.config.ID, len(batches))
	
	for i, batch := range batches {
		if c.CheckShutdown(sigChannel) {
			return
		}
		
		if err := c.ProcessBatch(batch, i+1, len(batches)); err != nil {
			log.Errorf("action: process_batch | result: fail | client_id: %v | batch: %d/%d | error: %v", 
				c.config.ID, i+1, len(batches), err)
			return
		}
	}

	log.Infof("action: loop_finished | result: success | client_id: %v | total_bets_processed: %d", c.config.ID, len(c.bets))
	
	if err := c.NotifyFinishedAndQueryWinners(); err != nil {
		log.Errorf("action: notify_finished_and_query_winners | result: fail | client_id: %v | error: %v", c.config.ID, err)
		return
	}
}

// CheckShutdown checks if shutdown was requested
func (c *Client) CheckShutdown(sigChannel chan os.Signal) bool {
	select {
	case <-sigChannel:
		if c.conn != nil {
			_ = c.conn.Close()
		}
		log.Infof("action: shutdown | result: success | client_id: %v", c.config.ID)
		return true
	default:
		return false
	}
}

// ProcessBatch handles the complete processing of a single batch
func (c *Client) ProcessBatch(batch *BetBatch, batchNum, totalBatches int) error {
	if err := c.createClientSocket(); err != nil {
		return err
	}
	defer c.conn.Close()
	
	if err := batch.SendBatchToServer(c.conn); err != nil {
		return err
	}
	
	return batch.ReceiveBatchResponse(c.conn)
}

// NotifyFinishedAndQueryWinners notifies the server that this agency has finished sending all bets
// and then queries for winners on the same connection
func (c *Client) NotifyFinishedAndQueryWinners() error {
	if err := c.createClientSocket(); err != nil {
		return err
	}
	defer c.conn.Close()
	
	message := fmt.Sprintf("FINISHED|%s\n", c.config.ID)
	
	if err := SendMessageWithHeader(c.conn, message); err != nil {
		return fmt.Errorf("failed to send finished message: %v", err)
	}
	
	// Wait for acknowledgment
	reader := bufio.NewReader(c.conn)
	response, err := reader.ReadString('\n')
	if err != nil {
		return fmt.Errorf("failed to read finished acknowledgment: %v", err)
	}
	
	if strings.TrimSpace(response) != "ACK" {
		return fmt.Errorf("unexpected response to finished notification: %s", response)
	}
	
	log.Infof("action: notify_finished | result: success | client_id: %v", c.config.ID)
	
	winnersMessage := fmt.Sprintf("QUERY_WINNERS|%s\n", c.config.ID)
	
	if err := SendMessageWithHeader(c.conn, winnersMessage); err != nil {
		return fmt.Errorf("failed to send winners query: %v", err)
	}
	
	// Read winners response
	response, err = reader.ReadString('\n')
	if err != nil {
		return fmt.Errorf("failed to read winners response: %v", err)
	}
	
	response = strings.TrimSpace(response)
	if strings.HasPrefix(response, "WINNERS|") {
		parts := strings.Split(response, "|")
		if len(parts) >= 2 {
			if len(parts) == 2 && parts[1] == "" {
				log.Infof("action: consulta_ganadores | result: success | cant_ganadores: 0")
				return nil
			}
			winnersCount := len(parts) - 1
			log.Infof("action: consulta_ganadores | result: success | cant_ganadores: %d", winnersCount)
			return nil
		}
	} else if strings.HasPrefix(response, "ERROR|") {
		parts := strings.Split(response, "|")
		if len(parts) >= 2 {
			errorMessage := strings.Join(parts[1:], "|")
			return fmt.Errorf("server_error: %s", errorMessage)
		}
	}
	
	return fmt.Errorf("unexpected_format: %s", response)
}


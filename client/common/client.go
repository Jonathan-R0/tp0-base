package common

import (
	"net"
	"os"
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
	
	// Create batches from all bets
	batches := CreateBatches(c.bets, c.config.MaxBatchAmount)
	log.Infof("action: batches_created | result: success | client_id: %v | total_batches: %d", 
		c.config.ID, len(batches))
	
	for batchIndex, batch := range batches {
		log.Debugf("action: process_batch | result: in_progress | client_id: %v | batch: %d/%d | bets_in_batch: %d", 
			c.config.ID, batchIndex+1, len(batches), len(batch.Bets))
		
		select {
		case <-sigChannel:
			if c.conn != nil {
				log.Debugf("action: close_connection_on_shutdown | result: in_progress | client_id: %v", c.config.ID)
				_ = c.conn.Close()
			}
			log.Infof("action: shutdown | result: success | client_id: %v", c.config.ID)
			return
		default:
			if err := c.createClientSocket(); err != nil {
				log.Errorf("action: process_batch | result: fail | client_id: %v | batch: %d/%d | error: connection failed: %v", 
					c.config.ID, batchIndex+1, len(batches), err)
				return
			}
			
			if err := batch.SendBatchToServer(c.conn); err != nil {
				log.Errorf("action: process_batch | result: fail | client_id: %v | batch: %d/%d | error: send failed: %v", 
					c.config.ID, batchIndex+1, len(batches), err)
				c.conn.Close()
				return
			}
			
			if err := batch.ReceiveBatchResponse(c.conn); err != nil {
				log.Errorf("action: process_batch | result: fail | client_id: %v | batch: %d/%d | error: receive failed: %v", 
					c.config.ID, batchIndex+1, len(batches), err)
				c.conn.Close()
				return
			}
			
			log.Debugf("action: close_connection | result: in_progress | client_id: %v | batch: %d/%d", c.config.ID, batchIndex+1, len(batches))
			c.conn.Close()
			
			log.Debugf("action: process_batch | result: success | client_id: %v | batch: %d/%d | bets_processed: %d", 
				c.config.ID, batchIndex+1, len(batches), len(batch.Bets))
		}
		
		if batchIndex < len(batches)-1 {
			log.Debugf("action: wait_between_batches | result: in_progress | client_id: %v | wait_time: %v", 
				c.config.ID, c.config.LoopPeriod)
			time.Sleep(c.config.LoopPeriod)
		}
	}

	log.Infof("action: loop_finished | result: success | client_id: %v | total_bets_processed: %d", c.config.ID, len(c.bets))
}

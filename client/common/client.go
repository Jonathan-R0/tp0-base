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
		
		c.WaitBetweenBatches(i, len(batches))
	}

	log.Infof("action: loop_finished | result: success | client_id: %v | total_bets_processed: %d", c.config.ID, len(c.bets))
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

// WaitBetweenBatches adds delay between batches if not the last one
func (c *Client) WaitBetweenBatches(currentIndex, totalBatches int) {
	if currentIndex < totalBatches-1 {
		time.Sleep(c.config.LoopPeriod)
	}
}

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
}

// Client Entity that encapsulates how
type Client struct {
	config ClientConfig
	conn   net.Conn
	bet Bet
}

// NewClient Initializes a new client receiving the configuration
// as a parameter
func NewClient(config ClientConfig, bet Bet) *Client {
	client := &Client{
		config: config,
		bet: bet,
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

// StartClientLoop Send messages to the client until some time threshold is met
func (c *Client) StartClientLoop(sigChannel chan os.Signal) {
	log.Infof("action: start_client_loop | result: in_progress | client_id: %v | loop_amount: %d | loop_period: %v", 
		c.config.ID, c.config.LoopAmount, c.config.LoopPeriod)
	
	// There is an autoincremental msgID to identify every message sent
	// Messages if the message amount threshold has not been surpassed
	for msgID := 1; msgID <= c.config.LoopAmount; msgID++ {
		log.Debugf("action: client_iteration | result: in_progress | client_id: %v | iteration: %d/%d", 
			c.config.ID, msgID, c.config.LoopAmount)
		
		// Create the connection the server in every loop iteration. Send an
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
				log.Errorf("action: client_iteration | result: fail | client_id: %v | iteration: %d | error: connection failed: %v", 
					c.config.ID, msgID, err)
				return
			}
			
			if err := c.bet.SendBetToServer(c.conn); err != nil {
				log.Errorf("action: client_iteration | result: fail | client_id: %v | iteration: %d | error: send failed: %v", 
					c.config.ID, msgID, err)
				c.conn.Close()
				return
			}
			
			c.bet.ReceiveBytesAndAssertAllDataMatches(c.conn)
			
			log.Debugf("action: close_connection | result: in_progress | client_id: %v | iteration: %d", c.config.ID, msgID)
			c.conn.Close()
			
			log.Debugf("action: client_iteration | result: success | client_id: %v | iteration: %d/%d", 
				c.config.ID, msgID, c.config.LoopAmount)
		}
		
		if msgID < c.config.LoopAmount {
			log.Debugf("action: wait_between_iterations | result: in_progress | client_id: %v | wait_time: %v", 
				c.config.ID, c.config.LoopPeriod)
			time.Sleep(c.config.LoopPeriod)
		}
	}

	log.Infof("action: loop_finished | result: success | client_id: %v", c.config.ID)
}

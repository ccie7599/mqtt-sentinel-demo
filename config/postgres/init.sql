-- MQTT Sentinel Database Initialization
-- This script creates the required tables for the authentication database

-- Create mqtt_clients table
CREATE TABLE IF NOT EXISTS mqtt_clients (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(255) UNIQUE NOT NULL,
    secret_hash VARCHAR(255) DEFAULT '',
    region VARCHAR(50) NOT NULL DEFAULT 'us-east',
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Create indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_mqtt_clients_client_id ON mqtt_clients(client_id);
CREATE INDEX IF NOT EXISTS idx_mqtt_clients_region ON mqtt_clients(region);
CREATE INDEX IF NOT EXISTS idx_mqtt_clients_enabled ON mqtt_clients(enabled);
CREATE INDEX IF NOT EXISTS idx_mqtt_clients_last_seen ON mqtt_clients(last_seen);

-- Create security_events table for logging
CREATE TABLE IF NOT EXISTS security_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'medium',
    source_ip VARCHAR(45),
    client_id VARCHAR(255),
    details JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for security events
CREATE INDEX IF NOT EXISTS idx_security_events_type ON security_events(event_type);
CREATE INDEX IF NOT EXISTS idx_security_events_severity ON security_events(severity);
CREATE INDEX IF NOT EXISTS idx_security_events_created_at ON security_events(created_at);
CREATE INDEX IF NOT EXISTS idx_security_events_client_id ON security_events(client_id);

-- Create a view for recent security events
CREATE OR REPLACE VIEW recent_security_events AS
SELECT
    id,
    event_type,
    severity,
    source_ip,
    client_id,
    details,
    created_at
FROM security_events
WHERE created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;

-- Insert a few sample users for testing
INSERT INTO mqtt_clients (client_id, secret_hash, region, enabled)
VALUES
    ('bridge-user', '', 'us-east', true),
    ('test-user-1', '', 'us-east', true),
    ('test-user-2', '', 'eu-west', true),
    ('test-user-3', '', 'ap-south', true)
ON CONFLICT (client_id) DO NOTHING;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO sentinel;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sentinel;

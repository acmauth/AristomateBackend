const express = require('express');
const path = require('path');
const cors = require('cors');

const app = express();
app.use(cors());
app.options('*', cors()) // include before other routes
const port = 8000; // You can change this to any port you prefer

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Proxy endpoint for token exchange
app.post('/api/auth/token', async (req, res) => {
  try {
    const tokenUrl = 'https://oauth2.it.auth.gr/auth/realms/universis/protocol/openid-connect/token';
    
    // Forward the request to the OAuth server
    const response = await fetch(tokenUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: new URLSearchParams(req.body).toString()
    });

    const data = await response.json();
    
    if (!response.ok) {
      return res.status(response.status).json(data);
    }

    res.json(data);
  } catch (error) {
    console.error('Token proxy error:', error);
    res.status(500).json({ error: 'Token exchange failed' });
  }
});

/**
 * Health check endpoint
 */
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});


// Serve static files from the current directory
app.use(express.static(path.join(__dirname, 'public')));

app.listen(port, () => {
    console.log(`Server is running on http://localhost:${port}`);
});


module.exports = app;
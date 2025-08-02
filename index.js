const functions = require("firebase-functions");
const express = require("express");
const cors = require("cors");

const app = express();

// --- CORRECT CORS CONFIGURATION ---
const allowedOrigins = [
  "https://brightacts.com",
  "https://www.brightacts.com",
  "https://brightacts-frontend-50f58.web.app",
  "https://brightacts-frontend-50f58.firebaseapp.com",
];

app.use(cors({
  origin: (origin, callback) => {
    // Allow requests with no origin (like mobile apps or curl requests)
    if (!origin) return callback(null, true);

    // Allow localhost requests for any port
    if (origin.startsWith("http://localhost:")) {
      return callback(null, true);
    }
    
    if (allowedOrigins.indexOf(origin) === -1) {
      const msg = "The CORS policy for this site does not allow access from the specified Origin.";
      return callback(new Error(msg), false);
    }
    
    return callback(null, true);
  }
}));
// ------------------------------------


// --- YOUR API ROUTES ---
app.get("/users/username-check/:username", (req, res) => {
  const username = req.params.username;
  console.log("Checking username:", username);
  // Your database logic here...
  res.status(200).send({ available: true });
});

// Add your other endpoints here...


// --- Export the Express app ---
exports.api = functions.https.onRequest(app);

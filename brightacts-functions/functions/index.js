require('dotenv').config(); 

const functions = require("firebase-functions");
const admin = require("firebase-admin");
const fetch = require("node-fetch");

admin.initializeApp();

// 🔹 Your backend API base URL
const BACKEND_URL = "https://peoples-coin-service-105378934751.us-central1.run.app";

exports.unifiedSignUp = functions.https.onRequest(async (req, res) => {
  res.set("Access-Control-Allow-Origin", "*");
  res.set("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.set("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(204).send("");
  }

  try {
    const { email, password, username, recaptchaToken } = req.body;

    if (!email || !password || !username) {
      return res.status(400).json({ error: "Missing required fields" });
    }

    // ✅ Create Firebase Auth User
    const userRecord = await admin.auth().createUser({
      email,
      password,
      displayName: username
    });

    // ✅ Verify reCAPTCHA (optional if already handled on backend)
    if (recaptchaToken) {
      const secretKey = functions.config().recaptcha.secret;
      const verifyUrl = `https://www.google.com/recaptcha/api/siteverify?secret=${secretKey}&response=${recaptchaToken}`;

      const recaptchaRes = await fetch(verifyUrl, { method: "POST" });
      const recaptchaJson = await recaptchaRes.json();

      if (!recaptchaJson.success) {
        return res.status(400).json({ error: "reCAPTCHA verification failed" });
      }
    }

    // ✅ Call your backend to register the user
    const backendResponse = await fetch(`${BACKEND_URL}/api/v1/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        firebase_uid: userRecord.uid,
        email,
        username
      })
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      return res.status(backendResponse.status).send(errorText);
    }

    return res.status(201).json({
      message: "User created successfully",
      uid: userRecord.uid
    });

  } catch (err) {
    console.error("Error in unifiedSignUp:", err);
    return res.status(500).json({ error: err.message });
  }
});


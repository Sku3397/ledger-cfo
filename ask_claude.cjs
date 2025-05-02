require('dotenv').config(); // Load .env file
// ask_claude.cjs (SDK Version - Improved Error Handling)
const Anthropic = require('@anthropic-ai/sdk');

async function askClaudeSDK(query) {
  console.log("Script started."); // Added log
  if (!query) {
    console.error("Usage: node ask_claude.cjs \"<Your question for Claude>\"");
    process.exitCode = 1; // Use exitCode
    return; // Allow process to exit naturally
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    console.error("Error: ANTHROPIC_API_KEY environment variable is not set.");
    console.error("Please set the ANTHROPIC_API_KEY before running this script.");
    process.exitCode = 1; // Use exitCode
    return; // Allow process to exit naturally
  }

  const anthropic = new Anthropic({
    apiKey: apiKey,
  });

  console.log(`Attempting to send query to Claude SDK: "${query}"`); // Added log

  try {
    const response = await anthropic.messages.create({
      model: "claude-3-opus-20240229", // Or your preferred model
      max_tokens: 1024,
      messages: [{ role: "user", content: query }],
    });

    console.log("Received response from Claude SDK."); // Added log

    let responseText = "";
    if (response.content && response.content.length > 0 && response.content[0].type === 'text') {
        responseText = response.content[0].text;
    } else {
        console.log("Claude response content was empty or not text."); // Added log
    }

    console.log(`Claude SDK Response:\n${responseText}`);
    // No need to explicitly set exitCode on success, 0 is default

  } catch (error) {
    console.error("Error during Claude SDK call:"); // Added log
    console.error(`Claude SDK Error: ${error.message}`);
    if (error.response && error.response.data) {
        console.error("API Error Details:", JSON.stringify(error.response.data, null, 2));
    } else if (error.request) {
        console.error("API Request Error: No response received.");
    } else {
        console.error("Error object:", error); // Log the whole error object for more details
    }
    process.exitCode = 1; // Use exitCode
    // Allow process to exit naturally after logging
  } finally {
      console.log("askClaudeSDK function finished."); // Added log
  }
}

// Get the query from command line arguments
const userQuery = process.argv.slice(2).join(' ');

askClaudeSDK(userQuery).then(() => {
    console.log(`Script finished execution. Exit code: ${process.exitCode || 0}`); // Added final log
}); 
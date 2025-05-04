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

// Get the query from command line arguments OR stdin
let userQuery = process.argv.slice(2).join(' ');

if (!userQuery) {
    console.log("No command line arguments provided. Reading query from stdin..."); // Added log
    const chunks = [];
    process.stdin.on('readable', () => {
        let chunk;
        while (null !== (chunk = process.stdin.read())) {
            chunks.push(chunk);
        }
    });
    process.stdin.on('end', () => {
        try { // Added try block for stdin processing
            userQuery = Buffer.concat(chunks).toString('utf8').trim();
            console.log("Finished reading from stdin."); // Added log
            if (!userQuery) {
                console.error("Error: No query provided via arguments or stdin.");
                process.exitCode = 1; // Use process.exitCode for graceful exit
                console.log(`Script finished execution. Exit code: ${process.exitCode || 0}`); // Log exit before exiting
                return; // Exit if no query after stdin
            }
            // Call the main function only after stdin is fully read and valid
            askClaudeSDK(userQuery).catch(err => { // Added catch for main function called from stdin path
                 console.error("Error during main execution (from stdin):", err);
                 process.exitCode = 2; // Set exit code 2 for internal script errors
            }).finally(() => {
                 console.log(`Script finished execution. Exit code: ${process.exitCode || 0}`); // Log exit code
            });
        } catch (stdinError) { // Added catch block for stdin processing
            console.error("Error processing stdin:", stdinError);
            process.exitCode = 2; // Indicate internal script error
            console.log(`Script finished execution. Exit code: ${process.exitCode || 0}`); // Log exit code
        }
    });
} else {
    // If query was provided via args, call main immediately
    askClaudeSDK(userQuery).catch(err => { // Added catch for main function called from args path
         console.error("Error during main execution (from args):", err);
         process.exitCode = 2; // Set exit code 2 for internal script errors
    }).finally(() => {
         console.log(`Script finished execution. Exit code: ${process.exitCode || 0}`); // Log exit code
    });
} 
import { validateRatingCreate } from './src/lib/schema-validator.js';

const data = {
  note_id: "note-rate-123",
  rater_participant_id: "rater-456",
  helpfulness_level: "HELPFUL"
};

try {
  validateRatingCreate(data);
  console.log("Valid!");
} catch (err) {
  console.log("Error:", err.message);
  console.log("Errors:", JSON.stringify(err.errors, null, 2));
  console.log("Data:", JSON.stringify(err.data, null, 2));
}

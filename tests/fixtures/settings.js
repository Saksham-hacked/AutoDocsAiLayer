const router = require('express').Router();

/**
 * GET /settings
 * Returns application settings
 */
router.get('/settings', async (req, res) => {
  const settings = await getSettings();
  res.json(settings);
});

module.exports = router;

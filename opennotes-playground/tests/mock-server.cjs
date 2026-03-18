const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const fixtures = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures.json"), "utf-8"),
);

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost`);
  const p = url.pathname;

  res.setHeader("Content-Type", "application/vnd.api+json");

  if (p.match(/\/api\/v2\/simulations\/[^/]+\/analysis\/detailed/)) {
    res.end(JSON.stringify(fixtures.detailed));
  } else if (p.match(/\/api\/v2\/simulations\/[^/]+\/analysis\/timeline/)) {
    res.end(JSON.stringify(fixtures.timeline));
  } else if (p.match(/\/api\/v2\/simulations\/[^/]+\/analysis$/)) {
    res.end(JSON.stringify(fixtures.analysis));
  } else if (p.match(/\/api\/v2\/simulations\/[^/]+$/)) {
    res.end(JSON.stringify(fixtures.simulation));
  } else {
    res.statusCode = 404;
    res.end(JSON.stringify({ error: "Not found", path: p }));
  }
});

const port = process.env.MOCK_PORT || 9999;
server.listen(port, () => {
  console.log(`Mock API server listening on port ${port}`);
});

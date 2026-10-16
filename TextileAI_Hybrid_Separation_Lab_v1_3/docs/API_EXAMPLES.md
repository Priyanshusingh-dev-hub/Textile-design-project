# API Examples

## Health
`GET /health`

## Demo analysis
`POST /api/analysis/demo`

## Candidate strategies
`POST /api/separation/candidates?gradient_score=0.18&max_inks=8`

## Commit a plan
`POST /api/separation/commit`
```json
{
  "settings": {
    "strategy": "hybrid",
    "max_inks": 8,
    "lpi": 45,
    "dpi": 300,
    "preserve_tones": true,
    "user_override": true
  },
  "ink_ids": ["navy", "pink-light", "pink-dark"]
}
```
The example endpoint currently accepts the settings model and `ink_ids` as request parameters; wire the production request body schema consistently before frontend integration.

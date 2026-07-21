# Compute facts from access.log

`access.log` in this directory is a web-server access log. Each line has
the format:

```
TIMESTAMP METHOD PATH STATUS_CODE RESPONSE_TIME_MS
```

Compute the following from the log and write the results to `answer.json`
in this same directory, with exactly these keys:

```json
{
  "total_requests": 0,
  "count_5xx": 0,
  "count_4xx": 0,
  "busiest_endpoint": "...",
  "busiest_endpoint_count": 0,
  "avg_response_ms_status_200": 0.0
}
```

Field definitions:
- `total_requests` — total number of log lines.
- `count_5xx` — number of requests with a status code in the 500-599 range.
- `count_4xx` — number of requests with a status code in the 400-499 range.
- `busiest_endpoint` — the `PATH` value with the most requests (ties: any
  such tied path is acceptable, but there is no tie in this log).
- `busiest_endpoint_count` — the request count for that endpoint.
- `avg_response_ms_status_200` — the mean `RESPONSE_TIME_MS` across only
  the requests with status code exactly 200, rounded to 1 decimal place.

Do not modify `access.log`. Show your work is not required — only
`answer.json`'s final values are graded.

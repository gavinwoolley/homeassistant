#!/bin/bash
curl --location --request POST 'https://#{home_assistant_base_url}#:599/grafana/api/annotations/graphite' \
--header 'Authorization: #{grafana_api_key}#' \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--insecure \
--data-raw '{
    "tags":  [
                 "Started",
                 "HomeAssistant",
                 "Service"
             ],
    "data":  "Home Assistant - Service Started",
    "what":  "Event Triggered"
}'
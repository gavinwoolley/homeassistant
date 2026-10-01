#!/bin/bash
curl --location --request POST 'https://#{home_assistant_base_url}#:599/grafana/api/annotations/graphite' \
--header 'Authorization: #{grafana_api_key}#' \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--insecure \
--data-raw '{
    "tags":  [
                 "Reboot",
                 "HomeAssistant",
                 "Server"
             ],
    "data":  "Home Assistant - Server Reboot",
    "what":  "Event Triggered"
}'

sudo /sbin/shutdown -r
# Post to Google TTS
param(
    [string]$Name
)
function Post-HomeAssistantTTS {
    param (
        $Message
    )
    # Send Audio to Google Home
    $JSON = @{
        "entity_id" = "media_player.lounge_speaker"
        "message"   = "$Message"
    } | ConvertTo-Json

    $root = "https://home.example.com:8123/"
    $uri = "api/services/tts/google_translate_say"
    $Token = "REDACTED_JWT"

    $Random = Get-Random -Maximum 1000
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    #$result = Invoke-WebRequest -uri "$($root)$($uri)" -Body $JSON -ContentType "application/json" -Headers @{'Authorization' = "Bearer $Token"} -Method Post

    # Send Persistant Notification to Home Screen
    $JSON = @{
        "notification_id" = "$Random"
        "title"           = "uTorrent Download Complete"
        "message"         = "$($Message)"
    } | ConvertTo-Json

    $uri = "api/services/persistent_notification/create"
    $result = Invoke-WebRequest -uri "$($root)$($uri)" -Body $JSON -ContentType "application/json" -Headers @{'Authorization' = "Bearer $Token" } -Method Post

}

Post-HomeAssistantTTS -Message "Message from uTorrent - $Name Download Complete"

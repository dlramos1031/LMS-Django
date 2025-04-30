# users/utils.py (or a similar utility file)

import requests
import json
from django.conf import settings # If you store API URL or tokens in settings
from users.models import UserDevice # Adjust import based on your UserDevice model location

# Expo's Push API endpoint
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

def send_expo_push_notification(user, title, body, data=None):
    """
    Sends a push notification to a specific user's registered devices via Expo.

    Args:
        user: The User object to send the notification to.
        title (str): The title of the notification.
        body (str): The main message content of the notification.
        data (dict, optional): Extra data to send with the notification,
                               which can be used by the app when it's opened
                               from the notification. Defaults to None.

    Returns:
        bool: True if the request to Expo was made successfully (doesn't guarantee delivery),
              False otherwise.
    """
    # Find active device tokens for the user
    # Assuming your UserDevice model has an 'is_active' field (recommended)
    # and a 'device_token' field storing the ExponentPushToken[...]
    # Adjust the filter based on your actual model fields
    user_devices = UserDevice.objects.filter(user=user, is_active=True)

    if not user_devices.exists():
        print(f"No active devices found for user {user.username}. Cannot send notification.")
        return False

    messages = []
    recipient_tokens = [] # Keep track of tokens for potential error handling

    for device in user_devices:
        token = device.device_token
        if not token or not token.startswith("ExponentPushToken["):
            print(f"Skipping invalid token for user {user.username}: {token}")
            continue

        message = {
            "to": token,
            "sound": "default", # Or None
            "title": title,
            "body": body,
            # Add priority and channelId if needed for Android
            # "priority": "high",
            # "channelId": "default", # Ensure this matches the channel set in the app
        }
        if data:
            message["data"] = data # Attach extra data if provided

        messages.append(message)
        recipient_tokens.append(token)

    if not messages:
        print(f"No valid tokens found to send notification for user {user.username}.")
        return False

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/json",
        # Add Authorization header if using Expo Access Tokens (optional for basic sending)
        # "Authorization": f"Bearer {settings.EXPO_ACCESS_TOKEN}",
    }

    print(f"Sending {len(messages)} push notification(s) to Expo API for user {user.username}...")

    try:
        # Make the POST request to Expo's API
        response = requests.post(
            EXPO_PUSH_URL,
            headers=headers,
            data=json.dumps(messages), # Send messages as a JSON array
            timeout=10 # Add a timeout
        )
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        response_data = response.json()
        print("Expo API Response:", response_data)

        # --- Basic Error Handling (Recommended) ---
        if 'data' in response_data:
            for i, ticket in enumerate(response_data['data']):
                 # Check for errors reported by Expo for specific tokens
                 if ticket.get('status') == 'error':
                     token_sent = recipient_tokens[i] # Get the token corresponding to this ticket
                     error_details = ticket.get('details', {})
                     error_code = error_details.get('error')

                     print(f"Error sending to token {token_sent}: {ticket.get('message')}")

                     # If Expo says the token is invalid, deactivate/delete it
                     if error_code == 'DeviceNotRegistered':
                         print(f"Token {token_sent} is invalid (DeviceNotRegistered). Deactivating.")
                         try:
                             # Find the specific device and mark it inactive or delete
                             invalid_device = UserDevice.objects.get(device_token=token_sent)
                             invalid_device.is_active = False
                             invalid_device.save(update_fields=['is_active'])
                             # Or: invalid_device.delete()
                         except UserDevice.DoesNotExist:
                             print(f"Could not find device with token {token_sent} to deactivate.")
                         except Exception as db_err:
                             print(f"Error deactivating token {token_sent}: {db_err}")
        # -----------------------------------------

        return True # Request was successfully sent to Expo

    except requests.exceptions.RequestException as e:
        print(f"Error sending push notification request to Expo: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during push notification sending: {e}")
        return False

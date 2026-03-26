from gtts import gTTS
import os

# Define the script with natural pauses
# The periods (.) and commas (,) create short natural breaks in the AI voice
script = (
    "Hey! Are you still out? ... "
    "Listen, I just realized I locked myself out of the house and I don't have my spare keys with me. ... "
    "How far away are you right now? ... "
    "Okay, great. Could you please head back now? I am standing outside and it is getting quite cold. ... "
    "Let me know when you are around the corner, okay? See you in a bit."
)

# Generate the speech
tts = gTTS(text=script, lang='en', tld='co.uk') # Using a British accent for a different tone

# Ensure the static folder exists
if not os.path.exists('static'):
    os.makedirs('static')

# Save the file
tts.save("static/fake_call_voice.mp3")
print("Realistic voice file 'fake_call_voice.mp3' has been created in the static folder.")
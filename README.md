# Banking Forms & Peripherals Assistant

A FastAPI-based application that provides banking form downloads and peripheral control functionality.

## Features

- **Banking Forms**: Download various banking forms (PDF) based on user requests
- **Peripheral Control**: Control system peripherals like volume, brightness, and camera
- **Voice Processing**: Audio processing capabilities using librosa
- **AI Assistant**: OpenAI-powered chat interface with Hindi-English responses

## Project Structure

```
├── main.py              # Main FastAPI application
├── frontend.html        # Web interface
├── requirements.txt     # Python dependencies
├── downloaded_forms/    # Banking PDF forms storage
└── manifest.json        # Application manifest
```

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your OpenAI API key in `main.py`

3. Run the application:
```bash
python main.py
```

## API Endpoints

- `POST /chat` - Chat with AI assistant
- `GET /download/{filename}` - Download banking forms
- `POST /upload` - Upload and process audio files

## Banking Forms Available

The application includes 50+ banking forms including:
- Account opening forms
- Account closure forms
- KYC forms
- PPF forms
- Loan application forms
- And many more...

## Technologies Used

- FastAPI
- OpenAI API
- librosa (audio processing)
- HTML/CSS/JavaScript frontend

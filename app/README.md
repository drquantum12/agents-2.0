<!-- for STT -->
brew install ffmpeg
pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu118 # (for CUDA, adjust if using MPS)
pip install -U openai-whisper


<!-- for TTS (using XTTS-v2)-->
# Example for CUDA 11.7
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu117
# For CPU only
pip install torch torchvision torchaudio
pip install TTS soundfile
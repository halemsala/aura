import interpreter; interpreter.api_base = 'http://localhost:11434/v1'; interpreter.model = 'openai/llama3.1:8b-instruct-q8_0'; interpreter.local = True; interpreter.chat()

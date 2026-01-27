import google.generativeai as genai

# Твой ключ
genai.configure(api_key="AIzaSyBH_PcefYezMJFOhkShyVC-1S2di5OH6y8")

print("🔍 СПИСОК ДОСТУПНЫХ МОДЕЛЕЙ:")
try:
    for m in genai.list_models():
        # Нам нужны только те, которые умеют генерировать контент
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ {m.name}")
except Exception as e:
    print(f"Ошибка при получении списка: {e}")
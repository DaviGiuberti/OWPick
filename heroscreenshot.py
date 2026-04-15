import mss
import mss.tools
import keyboard

monitor = {
    "left": 461,
    "top": 252,
    "width": 86,
    "height": 86
}

contador = 1  # começa no print1

def tirar_print():
    global contador
    
    with mss.mss() as sct:
        screenshot = sct.grab(monitor)
        
        nome_arquivo = f"print{contador}.jpg"
        mss.tools.to_png(screenshot.rgb, screenshot.size, output=nome_arquivo)
    
    print(f"{nome_arquivo} salvo!")
    contador += 1  # incrementa para o próximo

# Atalho TAB + 1
keyboard.add_hotkey('tab+1', tirar_print)

print("Pressione TAB + 1 para tirar print...")
keyboard.wait()
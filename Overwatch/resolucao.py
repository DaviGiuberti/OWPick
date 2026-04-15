import tkinter as tk
import pyautogui
import time
import sys

class AreaSelector:
    def __init__(self):
        # Mostrar contagem no console antes de abrir a janela
        print("A janela aparecerá em:")
        for i in range(3, 0, -1):
            print(f"{i}...")
            time.sleep(1)
        print("Selecione uma área!")
        
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.3)
        self.root.configure(bg='gray')
        self.root.attributes('-topmost', True)  # Garantir que fique sobre outras janelas
        
        self.start_x = None
        self.start_y = None
        self.rect = None
        
        self.canvas = tk.Canvas(self.root, cursor="cross", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        # Adicionar tecla ESC para cancelar
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        
        self.root.mainloop()
    
    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect:
            self.canvas.delete(self.rect)
    
    def on_drag(self, event):
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, event.x, event.y,
            outline="red", width=2
        )
    
    def on_release(self, event):
        end_x, end_y = event.x, event.y
        
        # Calcular left, top, width, height
        left = min(self.start_x, end_x)
        top = min(self.start_y, end_y)
        width = abs(end_x - self.start_x)
        height = abs(end_y - self.start_y)
        
        print(f"\nCoordenadas selecionadas:")
        print(f"'left': {left}, 'top': {top}, 'width': {width}, 'height': {height}")
        self.root.destroy()

# Executar o seletor
if __name__ == "__main__":
    AreaSelector()
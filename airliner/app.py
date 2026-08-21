"""Aplicación Airliner: cliente descargable para EvA."""

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from core import CajaNegra, ConectorMSFS


class AirlinerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("EvA Airliner")
        self.root.geometry("600x400")

        self.caja_negra = CajaNegra()
        self.msfs = ConectorMSFS()

        self.setup_ui()

    def setup_ui(self):
        """Configura la interfaz de usuario."""
        # Header
        header = ttk.Frame(self.root)
        header.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(header, text="EvA Airliner", font=("Arial", 16, "bold")).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text=f"Caja Negra: {self.caja_negra.caja_negra}",
            font=("Arial", 10),
            foreground="gray",
        ).pack(side=tk.LEFT, padx=20)

        # Status
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=10, pady=5)

        msfs_status = "✓ Conectado" if self.msfs.conectado else "✗ Desconectado"
        ttk.Label(status_frame, text=f"MSFS: {msfs_status}").pack(anchor=tk.W)

        # Vuelos guardados
        vuelos_frame = ttk.LabelFrame(self.root, text="Vuelos en Caja Negra")
        vuelos_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.vuelos_listbox = tk.Listbox(vuelos_frame, height=10)
        self.vuelos_listbox.pack(fill=tk.BOTH, expand=True)

        self.refresh_vuelos()

        # Botones
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(btn_frame, text="Grabar Vuelo", command=self.grabar_vuelo).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Refrescar", command=self.refresh_vuelos).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Subir a EvA", command=self.subir_eva).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Salir", command=self.root.quit).pack(side=tk.RIGHT, padx=5)

    def refresh_vuelos(self):
        """Actualiza la lista de vuelos."""
        self.vuelos_listbox.delete(0, tk.END)
        vuelos = self.caja_negra.listar_vuelos()
        for v in vuelos:
            self.vuelos_listbox.insert(tk.END, v.name)

    def grabar_vuelo(self):
        """Graba un vuelo de prueba."""
        try:
            data = {
                "tipo": "vuelo_msfs",
                "telemetria": self.msfs.leer_telemetria(),
            }
            filepath = self.caja_negra.guardar_vuelo(data, "TEST")
            messagebox.showinfo("Éxito", f"Vuelo guardado:\n{filepath.name}")
            self.refresh_vuelos()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo grabar vuelo: {e}")

    def subir_eva(self):
        """Sube vuelos a EvA (placeholder)."""
        messagebox.showinfo("Info", "Función de sincronización aún no implementada.")

    def run(self):
        """Inicia la aplicación."""
        self.root.mainloop()
        if self.msfs.conectado:
            self.msfs.desconectar()


def main():
    root = tk.Tk()
    app = AirlinerApp(root)
    app.run()


if __name__ == "__main__":
    main()

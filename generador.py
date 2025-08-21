import argparse

def main():
    parser = argparse.ArgumentParser(description="Generador Docker Compose")
    parser.add_argument("nombre", type=str, help="Nombre del Compose generado")
    parser.add_argument("cantidad_clientes", type=str, help="Cantidad de clientes")

    args = parser.parse_args()

    print(f"Generando Compose: '{args.nombre}' con {args.cantidad_clientes} clientes")

if __name__ == "__main__":
    main()

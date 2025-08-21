import argparse
import yaml

def generar_compose(nombre_archivo, cantidad_clientes):
    data = {
        'version': '1',
        'name': 'multiclient',
        'services': {
            f'cliente{i}': {
                'container_name': f'cliente{i}',
                'image': 'client:latest',
                'entrypoint': '/client',
                'environment': [
                    'CLI_ID=1',
                    'CLI_LOG_LEVEL=DEBUG'
                ],
                'networks': 'testing_net',
                'depends_on': 'server',
            }
            for i in range(1, int(cantidad_clientes) + 1)
        },
    }
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

def main():
    parser = argparse.ArgumentParser(description="Generador Docker Compose")
    parser.add_argument("nombre", type=str, help="Nombre del Compose generado")
    parser.add_argument("cantidad_clientes", type=int, help="Cantidad de clientes")

    args = parser.parse_args()

    print(f"Generando Compose: '{args.nombre}' con {args.cantidad_clientes} clientes")
    generar_compose(args.nombre, args.cantidad_clientes)

if __name__ == "__main__":
    main()

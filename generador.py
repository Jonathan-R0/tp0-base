import argparse
import yaml

def generar_compose(nombre_archivo, cantidad_clientes):
    servicios_cliente = {
        f'client{i}': {
            'container_name': f'client{i}',
            'image': 'client:latest',
            'entrypoint': '/client',
            'environment': [
                f'CLI_ID={i}',
                'CLI_LOG_LEVEL=DEBUG'
            ],
            'volumes': [
                './client/config.yaml:/config.yaml'
            ],
            'networks': ['testing_net'],
            'depends_on': ['server'],
        }
        for i in range(1, int(cantidad_clientes) + 1)
    }

    services = {
        'server': {
            'container_name': 'server',
            'image': 'server:latest',
            'entrypoint': 'python3 /main.py',
            'environment': [
                'PYTHONUNBUFFERED=1',
                'LOGGING_LEVEL=DEBUG'
            ],
            'volumes': [
                './server/config.ini:/config.ini'
            ],
            'networks': ['testing_net']
        },
        **servicios_cliente,
    }

    data = {
        'name': 'tp0',
        'services': services,
        'networks': {
            'testing_net': {
                'ipam': {
                    'driver': 'default',
                    'config': [
                        {'subnet': '172.25.125.0/24'}
                    ]
                }
            }
        }
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

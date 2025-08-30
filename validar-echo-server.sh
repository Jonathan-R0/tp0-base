#!/bin/bash

# Genero un mensaje random
MENSAJE="string_prueba_$(date +%s)"

# Busco el puerto del server del archivo de configuración
SERVER_PORT=$(grep "SERVER_PORT" ./server/config.ini | cut -d'=' -f2 | xargs)

if [ -z "$SERVER_PORT" ]; then
    SERVER_PORT=12345
fi

RESPUESTA=$(docker run --rm --network=tp0_testing_net busybox sh -c "echo '$MENSAJE' | nc server $SERVER_PORT")

if [ "$RESPUESTA" = "$MENSAJE" ]; then
  echo "action: test_echo_server | result: success"
else
  echo "action: test_echo_server | result: fail"
fi
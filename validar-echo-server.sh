#!/bin/bash
MENSAJE="ping" # Agrego un mensaje de prueba random
RESPUESTA=$(docker run --rm --network=tp0_testing_net busybox sh -c "echo '$MENSAJE' | nc server 12345")

if [ "$RESPUESTA" == "$MENSAJE" ]; then
  echo "action: test_echo_server | result: success"
else
  echo "action: test_echo_server | result: fail"
fi
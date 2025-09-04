# TP0: Docker + Comunicaciones + Concurrencia

| Jonathan David Rosenblatt | 104105 |
| ------------------------- | ------ |

# Entrega

Esta primera sección del readme corresponde a la entrega del trabajo práctico. La [consigna](#consigna) como tal quedará en la sección siguiente. Se agregan además la sección de [Extras y Aclaraciones](#extras-y-aclaraciones) al final del readme.

Agrego también la sección de [Correcciones](#correcciones).

## Ejercicio 1

En el ejercicio 1 decidí utilizar la librería PYYAML para escribir el archivo a partir de un objeto.

Para instalar esta librería se debe ejecutar el comando: `pip install pyyaml`.

## Ejercicio 3

El shell script de este ejercicio funciona generando un string random el cual será envíado al server y devuelto:

1. El string consiste de un valor fijo y un timestamp (dato aleatorio).
2. Luego el mismo busca el puerto en el archivo de configuración del server (o `12345` si no lo encuentra).
3. Se genera un contenedor basado en una imagen de `busybox` que será eliminada una vez termine la ejecución que se le asigna. Dentro de este nuevo contenedor, ejecutamos el programa (`nc server...`) que envía dentro de la red de nuestro contenedor un mensaje al server (puerto 12345) con el string generado previamente.
4. Si el server devuelve el mismo string que se le envió, se mostrará en consola el mensaje de éxito.

Aclaro que el sistema que ejecute esta prueba debe tener una imagen de `busybox` descargada. En caso de no tenerla, se puede descargar con el comando `$ docker pull busybox`.

## Ejercicio 5

Para comunicar al servidor y cliente se utiliza un socket tcp.

Los mensajes que se envían tienen el siguiente formato:

```
Agencia|Nombre|Apellido|DNI|FechaNacimiento|Numero\n
```

Previo al enviado del mensaje se envía el tamaño del mismo, usando dos bytes big endian, al servidor.

Una vez el servidor procesa la apuesta recibida responde al cliente con el mismo mensaje que recibió en un principio.

Cuando el cliente recibe la respuesta del servidor, verifica que todos los datos matcheen.

De fallar alguna parte del proceso, se loggea de forma detallada que evento causó el problema en cuestion.

## Ejercicio 6

El protocolo de enviado de bets en _batch_ es similar al del ejercicio 5, con la diferencia que en este caso se envían multiples apuestas por iteración de comunicación con el server. Los batches tienen un tamaño máximo configurable en el archivo `config.yaml` del cliente (parámetro `batch.maxAmount`) y tampoco pueden exceder los 8kb.

Similar al envíado individual, previo al envio del batch se envía el tamaño total del mismo en 2 bytes big endian y luego se envían las apuestas concatenadas, cada una con el formato descripto en el ejercicio 5. El char `\n` sigue siendo el separador entre apuestas.

```
Agencia1|Nombre1|Apellido1|DNI1|FechaNacimiento1|Numero1\nAgencia2|Nombre2|Apellido2|DNI2|FechaNacimiento2|Numero2\n...AgenciaN|NombreN|ApellidoN|DNIN|FechaNacimientoN|NumeroN\n
```

En este caso, el servidor responde con un mensaje `SUCCESS|<APUESTAS PROCESADAS>\n` si todas las apuestas fueron procesadas correctamente, o `FAIL|<APUESTAS PROCESADAS>\n` en caso contrario.

## Ejercicio 7

Para esta variación del protocolo, una vez el cliente envía todas las apuestas, se envía al server un mensaje `FINISHED|<AGENCIA>\n`, donde `<AGENCIA>` es el ID de la agencia que envió las apuestas. El servidor al recibir este mensaje, marca que la agencia en cuestión ha terminado de enviar apuestas. Siempre con el lockeo correspondiente para evitar condiciones de carrera. Si todas las agencias finalizaron de enviar apuestas, el servidor marca que la lotería ha finalizado en la variable `lottery_completed`. El servidor responde con `ACK\n` al cliente.

Posteriormente ese envía un mensaje especial al servidor indicando que quiere consultar los ganadores: `QUERY_WINNERS|<AGENCIA>\n`. Luego el servidor procesa la solicitud, busca los ganadores correspondientes a la agencia que realiza la consulta y responde con un mensaje que contiene la lista de documentos ganadores, separados por el delimitador `|`. Si no hay ganadores, el servidor responde igualmente con el encabezado pero sin documentos. El flujo de esta consulta es el siguiente:

- El cliente envía el mensaje `QUERY_WINNERS|<AGENCIA>\n`. Previo a esto se envía el largo del mensaje con dos bytes big endian.
- El servidor responde con el mensaje `WINNERS|<DOC1>|<DOC2>|...|<DOCN>\n` (si hay ganadores) o `WINNERS|\n` (si no hay ganadores).
- Si el proceso de lotería no ha concluido, el servidor responde con `ERROR|Lottery not yet completed\n`.
- El cliente leerá la respuesta del servidor hasta encontrar el carácter de nueva línea `\n`, y luego procesará el mensaje recibido.

Es importante notar que el cliente reintentará esta consulta unas veces más por si la lotería no ha concluido aún. Entiendo que esto no es lo ideal dado que esto implica tener un mecanismo de esperas y reintentos. Puede suceder que el cliente consulte los ganadores antes de que todas las agencias hayan terminado de enviar sus apuestas. En ese caso, el servidor no podrá responder la consulta y el cliente deberá reintentar. Una solución superior, que es la que implementa el ejercicio 8, consiste de que el servidor tiene la conexión abierta y notifica al cliente cuando la lotería haya concluido. Para esto necesitamos un mecanismo de sincronización concurrente, por lo que quedará bien implementado en el próximo ejercicio.

También denotamos que por cada tipo de mensaje que el cliente envía al servidor, se crea una conexión nueva. Esto se debe a que podría resultar conveniente que el servidor pueda atender múltiples mensajes de forma desacoplada, por si el cliente quisiera enviar consultas de forma no secuencial y con un orden ya predefinido.

## Ejercicio 8

Para manejar la concurrencia agrego en el server:

- Una lista de los threads que atienden a los clientes.
- Un lock para manejar el acceso a la lista de threads.
- Un cambio en el protocolo de comunicación para que el cliente pueda notificar al servidor que ha terminado de enviar apuestas y que desea consultar los ganadores inmediatamente después usando el mismo socket.

Cuando recibo una conexión, creo un nuevo thread para atender a ese cliente y lo agrego a la lista de threads con el lockeo correspondiente. Estas operaciones son concurrentes pues, a pesar de tener el GIL, como son I/O (aceptar conexiones y crear threads) el GIL se libera durante esas operaciones.

En cada ciclo de mi loop principal, ejecuto una llamada a mi recolector de threads basura, en la función `_cleanup_finished_threads`. Esta función itera sobre la lista de threads y elimina aquellos que ya terminaron su ejecución (chequeando con el método `is_alive()`).

Al momento de cerrar el servidor, hago un join de todos los threads de mi lista de atendedores.

Además, para sincronizar la respuesta a la solicitud de ganadores, utilizo una variable de condición (`threading.Condition`). Cuando una agencia envía la notificación de que ha terminado de enviar apuestas, el servidor verifica si todas las agencias han finalizado. Si es así, notifica a todos los threads que están esperando la consulta de ganadores para que puedan proceder.

Estas operaciones de espera y notificación, que usan la librería `threading`, liberan el GIL mientras esperan, permitiendo que otros threads se ejecuten. Las pocas operaciones que no son concurrentes (como modificar la lista de agencias que han terminado) son rápidas y no deberían causar un cuello de botella significativo.

## Extras y Aclaraciones

- Se agregó una gran cantidad de logs en el código, pues fue requerido para debuggear y hace más sencillo entender el flujo del sistema.
- Existe una discrepancia entre el _casing_ del cliente y el servidor. El cliente utiliza `camelCase` y el servidor `snake_case`. Esto se debe a que el código nuevo que se fue agregando, copió el estilo de código ya existente.
- La marca del tipo de retorno en las funciones del servidor están implementadas de la rama ej5 en adelante.
- Se implementaron estas funciones para evitar los short reads y short writes:

  - En el server al momento de recibir información con la función `recv_from_server`: Implementa un bucle que continúa leyendo hasta recibir todos los bytes esperados (primero lee 2 bytes para el tamaño del mensaje en el header, luego lee el mensaje completo):

  ```python
    while len(data) < size:
        remaining = size - len(data)
        packet = sock.recv(remaining)
        data += packet
  ```

  - En el server al momento de enviar información al cliente `send_all_bytes`: Hace que todos los bytes sean enviados, reintentando automáticamente si `socket.send()` no envía todos los bytes:

  ```python
    while total_sent < len(data):
        sent = socket.send(data[total_sent:])
        total_sent += sent
  ```

  - En el cliente se maneja el envío con la función `WriteAllBytes`: aplica el mismo patrón que en el servidor para asegurar que todos los bytes sean enviados:

  ```go
    for totalWritten < len(data) {
        n, err := conn.Write(data[totalWritten:])
        if err != nil {
            return fmt.Errorf("failed to write data: %v", err)
        }
        totalWritten += n
    }
  ```

  - Y finalmente en el cliente se maneja la recepción utilizando la función `ReadString()`, que lee hasta encontrar el carácter de nueva línea `\n`, asegurando que se recibe el mensaje completo:

  ```go
    reader := bufio.NewReader(c.conn)
    response, err := reader.ReadString('\n')
    if err != nil {
        return fmt.Errorf("failed to read finished acknowledgment: %v", err)
    }
  ```

### Elección de Librerías

Para el servidor en python decidí agregar las siguientes librerías:
- `argparse`: Para manejar argumentos de línea de comandos en el script de generación de Docker Compose. También permite recibir los parámetros de forma necesaria y ordenada.
- `yaml`: Para planchar un objeto hacia el archivo yaml de salida. Permite trabajar de forma programática y limpiar el contenido a serializar. Entiendo que así como existe esta ventaja también existe la desventaja de que la librería aumenta el peso y tiempo de procesamiento en comparación a lo que se puede conseguir escribiendo un string puro. A futuro entiendo que si necesito crear un software que vaya a ser distribuido o que pueda resultar ser una dependencia de otro software aparte, lo ideal es que este tenga la menor cantidad de dependencias posibles para evitar posibles puntos de fallos externos.
- `threading`: Se utiliza para manejar la concurrencia en el servidor. Permite crear threads para atender múltiples clientes simultáneamente y manejar la sincronización entre ellos. Esta librería es parte de la biblioteca estándar de Python, por lo que no añade dependencias externas. A pesar de existir el GIL, su uso es adecuado para operaciones I/O como las que mayoritariamente realiza el servidor.
- `signal`: Para manejar señales del sistema operativo, como SIGTERM, permitiendo que el servidor y cliente puedan cerrar de forma _graceful_. Esta librería también es parte de la biblioteca estándar de Python.

En el cliente decidí agregar las siguientes librerías:
- `strconv`: Para convertir strings a enteros. Utilizado para castear los datos entrantes por el archivo de configuración.
- `os/signal` & `syscall`: Para manejar señales del sistema operativo, como SIGTERM, permitiendo que el cliente pueda cerrar de forma _graceful_.
- `bufio`: Para manejar la lectura de datos desde el socket y leer hasta un `\n`.
- `encoding/binary`: Para manejar la conversión de enteros a bytes en formato big endian. Se usa para enviar el tamaño del mensaje al servidor.
- `encoding/csv`: Para leer los archivos CSV de apuestas.

## Correcciones

Agrego todas las correcciones que realicé luego de la reunión con el docente. Todas las correcciones se hicieron sobre la rama `ej8` y posteriormente subiré estos cambios a mi rama `master`.

- Evito crear una conexión nueva por cada batch de apuestas enviadas.
- Agrego el uso de un lock en el servidor para proteger la escritura de las apuestas en el archivo.
```python
    with self.storage_lock:
        store_bets(bets)
```
- Evito hacer un `sock.recv(2)` pues puede suceder un short read. En su lugar, hago un bucle que continúa leyendo hasta recibir los 2 bytes esperados.
```python
    size_bytes = b""
    while len(size_bytes) < 2:
        packet = sock.recv(2 - len(size_bytes))
        if not packet:
            raise ConnectionError("Connection closed before reading message size")
        size_bytes += packet
    
    size = int.from_bytes(size_bytes, byteorder='big')
```
- Agrego el uso de unl lock de protección de datos de apuestas, recientemente agregado para proteger la escritura de apueastas, al momento de leer las apuestas para buscar ganadores.
```python
    with storage_lock:
        agency_bets = [bet for bet in load_bets() if str(bet.agency) == agency_id]
        winners = [bet.document for bet in agency_bets if has_won(bet)]
```

# Consigna

En el presente repositorio se provee un esqueleto básico de cliente/servidor, en donde todas las dependencias del mismo se encuentran encapsuladas en containers. Los alumnos deberán resolver una guía de ejercicios incrementales, teniendo en cuenta las condiciones de entrega descritas al final de este enunciado.

El cliente (Golang) y el servidor (Python) fueron desarrollados en diferentes lenguajes simplemente para mostrar cómo dos lenguajes de programación pueden convivir en el mismo proyecto con la ayuda de containers, en este caso utilizando [Docker Compose](https://docs.docker.com/compose/).

## Instrucciones de uso

El repositorio cuenta con un **Makefile** que incluye distintos comandos en forma de targets. Los targets se ejecutan mediante la invocación de: **make \<target\>**. Los target imprescindibles para iniciar y detener el sistema son **docker-compose-up** y **docker-compose-down**, siendo los restantes targets de utilidad para el proceso de depuración.

Los targets disponibles son:

| target                | accion                                                                                                                                                                                                                                                                                                                                                                |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docker-compose-up`   | Inicializa el ambiente de desarrollo. Construye las imágenes del cliente y el servidor, inicializa los recursos a utilizar (volúmenes, redes, etc) e inicia los propios containers.                                                                                                                                                                                   |
| `docker-compose-down` | Ejecuta `docker-compose stop` para detener los containers asociados al compose y luego `docker-compose down` para destruir todos los recursos asociados al proyecto que fueron inicializados. Se recomienda ejecutar este comando al finalizar cada ejecución para evitar que el disco de la máquina host se llene de versiones de desarrollo y recursos sin liberar. |
| `docker-compose-logs` | Permite ver los logs actuales del proyecto. Acompañar con `grep` para lograr ver mensajes de una aplicación específica dentro del compose.                                                                                                                                                                                                                            |
| `docker-image`        | Construye las imágenes a ser utilizadas tanto en el servidor como en el cliente. Este target es utilizado por **docker-compose-up**, por lo cual se lo puede utilizar para probar nuevos cambios en las imágenes antes de arrancar el proyecto.                                                                                                                       |
| `build`               | Compila la aplicación cliente para ejecución en el _host_ en lugar de en Docker. De este modo la compilación es mucho más veloz, pero requiere contar con todo el entorno de Golang y Python instalados en la máquina _host_.                                                                                                                                         |

### Servidor

Se trata de un "echo server", en donde los mensajes recibidos por el cliente se responden inmediatamente y sin alterar.

Se ejecutan en bucle las siguientes etapas:

1. Servidor acepta una nueva conexión.
2. Servidor recibe mensaje del cliente y procede a responder el mismo.
3. Servidor desconecta al cliente.
4. Servidor retorna al paso 1.

### Cliente

se conecta reiteradas veces al servidor y envía mensajes de la siguiente forma:

1. Cliente se conecta al servidor.
2. Cliente genera mensaje incremental.
3. Cliente envía mensaje al servidor y espera mensaje de respuesta.
4. Servidor responde al mensaje.
5. Servidor desconecta al cliente.
6. Cliente verifica si aún debe enviar un mensaje y si es así, vuelve al paso 2.

### Ejemplo

Al ejecutar el comando `make docker-compose-up` y luego `make docker-compose-logs`, se observan los siguientes logs:

```
client1  | 2024-08-21 22:11:15 INFO     action: config | result: success | client_id: 1 | server_address: server:12345 | loop_amount: 5 | loop_period: 5s | log_level: DEBUG
client1  | 2024-08-21 22:11:15 INFO     action: receive_message | result: success | client_id: 1 | msg: [CLIENT 1] Message N°1
server   | 2024-08-21 22:11:14 DEBUG    action: config | result: success | port: 12345 | listen_backlog: 5 | logging_level: DEBUG
server   | 2024-08-21 22:11:14 INFO     action: accept_connections | result: in_progress
server   | 2024-08-21 22:11:15 INFO     action: accept_connections | result: success | ip: 172.25.125.3
server   | 2024-08-21 22:11:15 INFO     action: receive_message | result: success | ip: 172.25.125.3 | msg: [CLIENT 1] Message N°1
server   | 2024-08-21 22:11:15 INFO     action: accept_connections | result: in_progress
server   | 2024-08-21 22:11:20 INFO     action: accept_connections | result: success | ip: 172.25.125.3
server   | 2024-08-21 22:11:20 INFO     action: receive_message | result: success | ip: 172.25.125.3 | msg: [CLIENT 1] Message N°2
server   | 2024-08-21 22:11:20 INFO     action: accept_connections | result: in_progress
client1  | 2024-08-21 22:11:20 INFO     action: receive_message | result: success | client_id: 1 | msg: [CLIENT 1] Message N°2
server   | 2024-08-21 22:11:25 INFO     action: accept_connections | result: success | ip: 172.25.125.3
server   | 2024-08-21 22:11:25 INFO     action: receive_message | result: success | ip: 172.25.125.3 | msg: [CLIENT 1] Message N°3
client1  | 2024-08-21 22:11:25 INFO     action: receive_message | result: success | client_id: 1 | msg: [CLIENT 1] Message N°3
server   | 2024-08-21 22:11:25 INFO     action: accept_connections | result: in_progress
server   | 2024-08-21 22:11:30 INFO     action: accept_connections | result: success | ip: 172.25.125.3
server   | 2024-08-21 22:11:30 INFO     action: receive_message | result: success | ip: 172.25.125.3 | msg: [CLIENT 1] Message N°4
server   | 2024-08-21 22:11:30 INFO     action: accept_connections | result: in_progress
client1  | 2024-08-21 22:11:30 INFO     action: receive_message | result: success | client_id: 1 | msg: [CLIENT 1] Message N°4
server   | 2024-08-21 22:11:35 INFO     action: accept_connections | result: success | ip: 172.25.125.3
server   | 2024-08-21 22:11:35 INFO     action: receive_message | result: success | ip: 172.25.125.3 | msg: [CLIENT 1] Message N°5
client1  | 2024-08-21 22:11:35 INFO     action: receive_message | result: success | client_id: 1 | msg: [CLIENT 1] Message N°5
server   | 2024-08-21 22:11:35 INFO     action: accept_connections | result: in_progress
client1  | 2024-08-21 22:11:40 INFO     action: loop_finished | result: success | client_id: 1
client1 exited with code 0
```

## Parte 1: Introducción a Docker

En esta primera parte del trabajo práctico se plantean una serie de ejercicios que sirven para introducir las herramientas básicas de Docker que se utilizarán a lo largo de la materia. El entendimiento de las mismas será crucial para el desarrollo de los próximos TPs.

### Ejercicio N°1:

Definir un script de bash `generar-compose.sh` que permita crear una definición de Docker Compose con una cantidad configurable de clientes. El nombre de los containers deberá seguir el formato propuesto: client1, client2, client3, etc.

El script deberá ubicarse en la raíz del proyecto y recibirá por parámetro el nombre del archivo de salida y la cantidad de clientes esperados:

`./generar-compose.sh docker-compose-dev.yaml 5`

Considerar que en el contenido del script pueden invocar un subscript de Go o Python:

```
#!/bin/bash
echo "Nombre del archivo de salida: $1"
echo "Cantidad de clientes: $2"
python3 mi-generador.py $1 $2
```

En el archivo de Docker Compose de salida se pueden definir volúmenes, variables de entorno y redes con libertad, pero recordar actualizar este script cuando se modifiquen tales definiciones en los sucesivos ejercicios.

### Ejercicio N°2:

Modificar el cliente y el servidor para lograr que realizar cambios en el archivo de configuración no requiera reconstruír las imágenes de Docker para que los mismos sean efectivos. La configuración a través del archivo correspondiente (`config.ini` y `config.yaml`, dependiendo de la aplicación) debe ser inyectada en el container y persistida por fuera de la imagen (hint: `docker volumes`).

### Ejercicio N°3:

Crear un script de bash `validar-echo-server.sh` que permita verificar el correcto funcionamiento del servidor utilizando el comando `netcat` para interactuar con el mismo. Dado que el servidor es un echo server, se debe enviar un mensaje al servidor y esperar recibir el mismo mensaje enviado.

En caso de que la validación sea exitosa imprimir: `action: test_echo_server | result: success`, de lo contrario imprimir:`action: test_echo_server | result: fail`.

El script deberá ubicarse en la raíz del proyecto. Netcat no debe ser instalado en la máquina _host_ y no se pueden exponer puertos del servidor para realizar la comunicación (hint: `docker network`). `

### Ejercicio N°4:

Modificar servidor y cliente para que ambos sistemas terminen de forma _graceful_ al recibir la signal SIGTERM. Terminar la aplicación de forma _graceful_ implica que todos los _file descriptors_ (entre los que se encuentran archivos, sockets, threads y procesos) deben cerrarse correctamente antes que el thread de la aplicación principal muera. Loguear mensajes en el cierre de cada recurso (hint: Verificar que hace el flag `-t` utilizado en el comando `docker compose down`).

## Parte 2: Repaso de Comunicaciones

Las secciones de repaso del trabajo práctico plantean un caso de uso denominado **Lotería Nacional**. Para la resolución de las mismas deberá utilizarse como base el código fuente provisto en la primera parte, con las modificaciones agregadas en el ejercicio 4.

### Ejercicio N°5:

Modificar la lógica de negocio tanto de los clientes como del servidor para nuestro nuevo caso de uso.

#### Cliente

Emulará a una _agencia de quiniela_ que participa del proyecto. Existen 5 agencias. Deberán recibir como variables de entorno los campos que representan la apuesta de una persona: nombre, apellido, DNI, nacimiento, numero apostado (en adelante 'número'). Ej.: `NOMBRE=Santiago Lionel`, `APELLIDO=Lorca`, `DOCUMENTO=30904465`, `NACIMIENTO=1999-03-17` y `NUMERO=7574` respectivamente.

Los campos deben enviarse al servidor para dejar registro de la apuesta. Al recibir la confirmación del servidor se debe imprimir por log: `action: apuesta_enviada | result: success | dni: ${DNI} | numero: ${NUMERO}`.

#### Servidor

Emulará a la _central de Lotería Nacional_. Deberá recibir los campos de la cada apuesta desde los clientes y almacenar la información mediante la función `store_bet(...)` para control futuro de ganadores. La función `store_bet(...)` es provista por la cátedra y no podrá ser modificada por el alumno.
Al persistir se debe imprimir por log: `action: apuesta_almacenada | result: success | dni: ${DNI} | numero: ${NUMERO}`.

#### Comunicación:

Se deberá implementar un módulo de comunicación entre el cliente y el servidor donde se maneje el envío y la recepción de los paquetes, el cual se espera que contemple:

- Definición de un protocolo para el envío de los mensajes.
- Serialización de los datos.
- Correcta separación de responsabilidades entre modelo de dominio y capa de comunicación.
- Correcto empleo de sockets, incluyendo manejo de errores y evitando los fenómenos conocidos como [_short read y short write_](https://cs61.seas.harvard.edu/site/2018/FileDescriptors/).

### Ejercicio N°6:

Modificar los clientes para que envíen varias apuestas a la vez (modalidad conocida como procesamiento por _chunks_ o _batchs_).
Los _batchs_ permiten que el cliente registre varias apuestas en una misma consulta, acortando tiempos de transmisión y procesamiento.

La información de cada agencia será simulada por la ingesta de su archivo numerado correspondiente, provisto por la cátedra dentro de `.data/datasets.zip`.
Los archivos deberán ser inyectados en los containers correspondientes y persistido por fuera de la imagen (hint: `docker volumes`), manteniendo la convencion de que el cliente N utilizara el archivo de apuestas `.data/agency-{N}.csv` .

En el servidor, si todas las apuestas del _batch_ fueron procesadas correctamente, imprimir por log: `action: apuesta_recibida | result: success | cantidad: ${CANTIDAD_DE_APUESTAS}`. En caso de detectar un error con alguna de las apuestas, debe responder con un código de error a elección e imprimir: `action: apuesta_recibida | result: fail | cantidad: ${CANTIDAD_DE_APUESTAS}`.

La cantidad máxima de apuestas dentro de cada _batch_ debe ser configurable desde config.yaml. Respetar la clave `batch: maxAmount`, pero modificar el valor por defecto de modo tal que los paquetes no excedan los 8kB.

Por su parte, el servidor deberá responder con éxito solamente si todas las apuestas del _batch_ fueron procesadas correctamente.

### Ejercicio N°7:

Modificar los clientes para que notifiquen al servidor al finalizar con el envío de todas las apuestas y así proceder con el sorteo.
Inmediatamente después de la notificacion, los clientes consultarán la lista de ganadores del sorteo correspondientes a su agencia.
Una vez el cliente obtenga los resultados, deberá imprimir por log: `action: consulta_ganadores | result: success | cant_ganadores: ${CANT}`.

El servidor deberá esperar la notificación de las 5 agencias para considerar que se realizó el sorteo e imprimir por log: `action: sorteo | result: success`.
Luego de este evento, podrá verificar cada apuesta con las funciones `load_bets(...)` y `has_won(...)` y retornar los DNI de los ganadores de la agencia en cuestión. Antes del sorteo no se podrán responder consultas por la lista de ganadores con información parcial.

Las funciones `load_bets(...)` y `has_won(...)` son provistas por la cátedra y no podrán ser modificadas por el alumno.

No es correcto realizar un broadcast de todos los ganadores hacia todas las agencias, se espera que se informen los DNIs ganadores que correspondan a cada una de ellas.

## Parte 3: Repaso de Concurrencia

En este ejercicio es importante considerar los mecanismos de sincronización a utilizar para el correcto funcionamiento de la persistencia.

### Ejercicio N°8:

Modificar el servidor para que permita aceptar conexiones y procesar mensajes en paralelo. En caso de que el alumno implemente el servidor en Python utilizando _multithreading_, deberán tenerse en cuenta las [limitaciones propias del lenguaje](https://wiki.python.org/moin/GlobalInterpreterLock).

## Condiciones de Entrega

Se espera que los alumnos realicen un _fork_ del presente repositorio para el desarrollo de los ejercicios y que aprovechen el esqueleto provisto tanto (o tan poco) como consideren necesario.

Cada ejercicio deberá resolverse en una rama independiente con nombres siguiendo el formato `ej${Nro de ejercicio}`. Se permite agregar commits en cualquier órden, así como crear una rama a partir de otra, pero al momento de la entrega deberán existir 8 ramas llamadas: ej1, ej2, ..., ej7, ej8.
(hint: verificar listado de ramas y últimos commits con `git ls-remote`)

Se espera que se redacte una sección del README en donde se indique cómo ejecutar cada ejercicio y se detallen los aspectos más importantes de la solución provista, como ser el protocolo de comunicación implementado (Parte 2) y los mecanismos de sincronización utilizados (Parte 3).

Se proveen [pruebas automáticas](https://github.com/7574-sistemas-distribuidos/tp0-tests) de caja negra. Se exige que la resolución de los ejercicios pase tales pruebas, o en su defecto que las discrepancias sean justificadas y discutidas con los docentes antes del día de la entrega. El incumplimiento de las pruebas es condición de desaprobación, pero su cumplimiento no es suficiente para la aprobación. Respetar las entradas de log planteadas en los ejercicios, pues son las que se chequean en cada uno de los tests.

La corrección personal tendrá en cuenta la calidad del código entregado y casos de error posibles, se manifiesten o no durante la ejecución del trabajo práctico. Se pide a los alumnos leer atentamente y **tener en cuenta** los criterios de corrección informados [en el campus](https://campusgrado.fi.uba.ar/mod/page/view.php?id=73393).

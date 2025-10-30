# conf-valkey-cluster-7.2

Docker Compose configuration for Valkey cluster 7.2

**Testing with OrbStack & macOS**

## Usage

Initialize Cluster

```bash
$ chmod +x ./init.sh

$ ./init.sh
```

Manual Start & Stop

```bash
docker-compose down

docker-compose up -d
```

Connect

```bash
$ docker inspect valkey-7000 | grep IPAddress
"Secondary**IPAddress**es": null,
"**IPAddress**": "",
	"**IPAddress**": "192.168.97.2",
         
                    
$ redis-cli -c -h 192.168.97.2 -p 7000 ping
PONG
```

or with local DNS (requires OrbStack)

```bash
$ redis-cli -c -h valkey-7000.valkey-cluster-72.orb.local -p 7000 ping
PONG
```

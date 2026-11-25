## Qué cambia y por qué

<!-- Una o dos frases. -->

## Cómo se probó

- [ ] `make test` en verde
- [ ] Si cambió un endpoint: `make openapi` (el contrato en `docs/openapi.json` debe coincidir con el código)

## ¿Rompe el contrato con quienes consumen la API?

- [ ] No
- [ ] Sí: sube la versión mayor y hay que avisar a los demás grupos antes de fusionar

<!-- Los PR van a `develop`. `main` solo recibe versiones (release) y dispara el despliegue a Azure. -->

class ServicioNoDisponible(Exception):
    """Un servicio del que depende el MID no respondió bien.

    `servicio` dice cuál (por ejemplo «flota-crud» o «viajes-zonas») y `motivo` es corto y seguro de mostrar.
    """

    def __init__(self, servicio: str, motivo: str):
        super().__init__(f"{servicio}: {motivo}")
        self.servicio = servicio
        self.motivo = motivo

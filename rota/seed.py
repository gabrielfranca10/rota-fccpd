"""Dados fictícios de demonstração (entregadores e restaurantes)."""

ENTREGADORES = [
    {"entregador_id": "ent-joao", "nome": "João Pereira", "veiculo": "moto", "capacidade": 4},
    {"entregador_id": "ent-marcia", "nome": "Márcia Souza", "veiculo": "moto", "capacidade": 4},
    {"entregador_id": "ent-caio", "nome": "Caio Ramos", "veiculo": "bike", "capacidade": 2},
    {"entregador_id": "ent-duda", "nome": "Duda Nascimento", "veiculo": "carro", "capacidade": 5},
]
NOMES_RESTAURANTE = ["Burger Rota", "Sushi Kaze", "Pizza da Esquina", "Cantina Napoli",
                     "Wok Express", "Tempero Nordestino", "Veggie House", "Taco Loco"]
ENDERECOS = ["Rua das Flores, 100", "Av. Boa Viagem, 2200", "Rua do Bom Jesus, 45",
            "Av. Conde da Boa Vista, 900", "Rua da Aurora, 300"]


def restaurante_id(i: int) -> str:
    return f"rest-{i:04d}"


def popular(nucleo, n_restaurantes: int = 20) -> None:
    for e in ENTREGADORES:
        nucleo.cadastrar_entregador(e)
    for i in range(n_restaurantes):
        nucleo.cadastrar_restaurante({
            "restaurante_id": restaurante_id(i),
            "nome": f"{NOMES_RESTAURANTE[i % len(NOMES_RESTAURANTE)]} {i // len(NOMES_RESTAURANTE) + 1}",
            "endereco": ENDERECOS[i % len(ENDERECOS)],
        })

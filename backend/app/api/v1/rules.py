from typing import List
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import CategorizationRule, Category, Transaction, User, MatchType
from app.schemas.rule import RuleCreate, RuleUpdate, RuleResponse, RuleTest, RuleTestResult
from app.utils.security import get_current_active_user

router = APIRouter()


def test_rule_match(pattern: str, match_type: MatchType, text: str) -> tuple[bool, str]:
    """Testa se uma regra corresponde ao texto."""
    text_lower = text.lower()
    pattern_lower = pattern.lower()

    if match_type == MatchType.CONTAINS:
        if pattern_lower in text_lower:
            return True, pattern
    elif match_type == MatchType.STARTS_WITH:
        if text_lower.startswith(pattern_lower):
            return True, pattern
    elif match_type == MatchType.ENDS_WITH:
        if text_lower.endswith(pattern_lower):
            return True, pattern
    elif match_type == MatchType.EXACT:
        if text_lower == pattern_lower:
            return True, pattern
    elif match_type == MatchType.REGEX:
        try:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return True, match.group()
        except re.error:
            pass

    return False, ""


@router.get("", response_model=List[RuleResponse])
def list_rules(
    active_only: bool = True,
    category_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Listar regras de categorização."""
    query = db.query(CategorizationRule)

    if active_only:
        query = query.filter(CategorizationRule.is_active == True)
    if category_id:
        query = query.filter(CategorizationRule.category_id == category_id)

    rules = query.order_by(CategorizationRule.priority.desc()).all()

    result = []
    for rule in rules:
        r = RuleResponse.model_validate(rule)
        r.category_name = rule.category.name if rule.category else None
        result.append(r)

    return result


@router.get("/{rule_id}", response_model=RuleResponse)
def get_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obter regra por ID."""
    rule = db.query(CategorizationRule).filter(CategorizationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    result = RuleResponse.model_validate(rule)
    result.category_name = rule.category.name if rule.category else None
    return result


@router.post("", response_model=RuleResponse)
def create_rule(
    rule_data: RuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Criar nova regra de categorização."""
    # Verificar se categoria existe
    category = db.query(Category).filter(Category.id == rule_data.category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Validar regex se for o tipo
    if rule_data.match_type == MatchType.REGEX:
        try:
            re.compile(rule_data.pattern)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Expressão regular inválida: {e}")

    rule = CategorizationRule(**rule_data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)

    result = RuleResponse.model_validate(rule)
    result.category_name = category.name
    return result


@router.put("/{rule_id}", response_model=RuleResponse)
def update_rule(
    rule_id: int,
    rule_data: RuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Atualizar regra."""
    rule = db.query(CategorizationRule).filter(CategorizationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    update_data = rule_data.model_dump(exclude_unset=True)

    # Verificar categoria (se informada)
    if "category_id" in update_data:
        category = db.query(Category).filter(Category.id == update_data["category_id"]).first()
        if not category:
            raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Validar regex se for o tipo
    match_type = update_data.get("match_type", rule.match_type)
    pattern = update_data.get("pattern", rule.pattern)
    if match_type == MatchType.REGEX:
        try:
            re.compile(pattern)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Expressão regular inválida: {e}")

    for field, value in update_data.items():
        setattr(rule, field, value)

    db.commit()
    db.refresh(rule)

    result = RuleResponse.model_validate(rule)
    result.category_name = rule.category.name if rule.category else None
    return result


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Excluir regra."""
    rule = db.query(CategorizationRule).filter(CategorizationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    db.delete(rule)
    db.commit()
    return {"message": "Regra excluída com sucesso"}


@router.post("/test", response_model=RuleTestResult)
def test_rule(
    data: RuleTest,
    current_user: User = Depends(get_current_active_user)
):
    """Testar uma regra contra um texto."""
    matches, matched_text = test_rule_match(data.pattern, data.match_type, data.test_text)
    return RuleTestResult(matches=matches, matched_text=matched_text if matches else None)


@router.post("/seed")
def seed_common_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Inserir regras de categorização comuns para cartões brasileiros.

    Cria regras CONTAINS para merchants conhecidos, associando a categorias existentes.
    Pula regras para categorias que não existem ou regras que já existem.
    """
    SEED_RULES = [
        # ═══════════════════════════════════════════════════
        # RESTAURANTE (~25 regras)
        # ═══════════════════════════════════════════════════
        ("ifood", "contains", "Restaurante"),
        ("ifd*", "contains", "Restaurante"),
        ("99food", "contains", "Restaurante"),
        ("rappi", "contains", "Restaurante"),
        ("restaurante", "contains", "Restaurante"),
        ("pizzaria", "contains", "Restaurante"),
        ("lanchonete", "contains", "Restaurante"),
        ("padaria", "contains", "Restaurante"),
        ("burger", "contains", "Restaurante"),
        ("busger", "contains", "Restaurante"),
        ("pecorelle", "contains", "Restaurante"),
        ("churrasq", "contains", "Restaurante"),
        ("oriental", "contains", "Restaurante"),
        ("calle 54", "contains", "Restaurante"),
        ("mania prime", "contains", "Restaurante"),
        ("praca panamericana", "contains", "Restaurante"),
        ("santa cla", "contains", "Restaurante"),
        ("moema servicos", "contains", "Restaurante"),
        ("outback", "contains", "Restaurante"),
        ("madero", "contains", "Restaurante"),
        ("mcdonald", "contains", "Restaurante"),
        ("subway", "contains", "Restaurante"),
        ("starbucks", "contains", "Restaurante"),
        ("kfc", "contains", "Restaurante"),
        ("habib", "contains", "Restaurante"),
        ("nagumo", "contains", "Restaurante"),
        ("uber eats", "contains", "Restaurante"),
        ("zdelivery", "contains", "Restaurante"),
        ("bob's", "contains", "Restaurante"),
        ("china in box", "contains", "Restaurante"),
        ("spoleto", "contains", "Restaurante"),
        ("giraffas", "contains", "Restaurante"),
        ("coco bambu", "contains", "Restaurante"),

        # ═══════════════════════════════════════════════════
        # SUPERMERCADO (~18 regras)
        # ═══════════════════════════════════════════════════
        ("supermercado", "contains", "Supermercado"),
        ("carrefour", "contains", "Supermercado"),
        ("daki", "contains", "Supermercado"),
        ("extra hiper", "contains", "Supermercado"),
        ("pao de acucar", "contains", "Supermercado"),
        ("assai", "contains", "Supermercado"),
        ("atacadao", "contains", "Supermercado"),
        ("hortifruti", "contains", "Supermercado"),
        ("natural da terra", "contains", "Supermercado"),
        ("st marche", "contains", "Supermercado"),
        ("sao roque", "contains", "Supermercado"),
        ("hirota", "contains", "Supermercado"),
        ("big bompreco", "contains", "Supermercado"),
        ("dia superm", "contains", "Supermercado"),
        ("oba hortifruti", "contains", "Supermercado"),
        ("emporio santa", "contains", "Supermercado"),
        ("mambo", "contains", "Supermercado"),
        ("minuto pao", "contains", "Supermercado"),

        # ═══════════════════════════════════════════════════
        # TRANSPORTES (~15 regras)
        # ═══════════════════════════════════════════════════
        ("99app", "contains", "Transportes"),
        ("dl*99 ride", "contains", "Transportes"),
        ("dl*99", "contains", "Transportes"),
        ("uber trip", "contains", "Transportes"),
        ("uber *trip", "contains", "Transportes"),
        ("tagitau", "contains", "Transportes"),
        ("sem parar", "contains", "Transportes"),
        ("semparar", "contains", "Transportes"),
        ("connectcar", "contains", "Transportes"),
        ("pedagio", "contains", "Transportes"),
        ("pedágio", "contains", "Transportes"),
        ("estaciona", "contains", "Transportes"),
        ("estapar", "contains", "Transportes"),
        ("zona azul", "contains", "Transportes"),
        ("veloe", "contains", "Transportes"),
        ("moovit", "contains", "Transportes"),

        # ═══════════════════════════════════════════════════
        # LAZER / ASSINATURAS (~30 regras)
        # ═══════════════════════════════════════════════════
        ("netflix", "contains", "Lazer"),
        ("spotify", "contains", "Lazer"),
        ("disney", "contains", "Lazer"),
        ("amazon prime", "contains", "Lazer"),
        ("amazonprimebr", "contains", "Lazer"),
        ("amazon ad free", "contains", "Lazer"),
        ("amazon prime canais", "contains", "Lazer"),
        ("applecombill", "contains", "Lazer"),
        ("apple.com", "contains", "Lazer"),
        ("google youtube", "contains", "Lazer"),
        ("claude.ai", "contains", "Lazer"),
        ("folhadespaulo", "contains", "Lazer"),
        ("nytim", "contains", "Lazer"),
        ("ny times", "contains", "Lazer"),
        ("wix.com", "contains", "Lazer"),
        ("f1 tv", "contains", "Lazer"),
        ("produtosuol", "contains", "Lazer"),
        ("wsj", "contains", "Lazer"),
        ("minimalclub", "contains", "Lazer"),
        ("twilio", "contains", "Lazer"),
        ("microsoft", "contains", "Lazer"),
        ("ingresso.com", "contains", "Lazer"),
        ("steamgames", "contains", "Lazer"),
        ("steam games", "contains", "Lazer"),
        ("loteriasonline", "contains", "Lazer"),
        ("picpay", "contains", "Lazer"),
        ("hbo max", "contains", "Lazer"),
        ("max.com", "contains", "Lazer"),
        ("paramount", "contains", "Lazer"),
        ("globoplay", "contains", "Lazer"),
        ("crunchyroll", "contains", "Lazer"),
        ("deezer", "contains", "Lazer"),
        ("playstation", "contains", "Lazer"),
        ("xbox", "contains", "Lazer"),
        ("cinema", "contains", "Lazer"),
        ("cinemark", "contains", "Lazer"),
        ("openai", "contains", "Lazer"),
        ("chatgpt", "contains", "Lazer"),

        # ═══════════════════════════════════════════════════
        # SAÚDE (~18 regras)
        # ═══════════════════════════════════════════════════
        ("prudential", "contains", "Saúde"),
        ("prudent*", "contains", "Saúde"),
        ("farmacia", "contains", "Saúde"),
        ("farmácia", "contains", "Saúde"),
        ("drogaria", "contains", "Saúde"),
        ("droga raia", "contains", "Saúde"),
        ("drogaraia", "contains", "Saúde"),
        ("drogasil", "contains", "Saúde"),
        ("pacheco", "contains", "Saúde"),
        ("sulamerica", "contains", "Saúde"),
        ("amil", "contains", "Saúde"),
        ("hapvida", "contains", "Saúde"),
        ("unimed", "contains", "Saúde"),
        ("fleury", "contains", "Saúde"),
        ("dasa", "contains", "Saúde"),
        ("einstein", "contains", "Saúde"),
        ("laboratorio", "contains", "Saúde"),
        ("laboratório", "contains", "Saúde"),
        ("hospital", "contains", "Saúde"),
        ("clinica", "contains", "Saúde"),
        ("clínica", "contains", "Saúde"),
        ("odonto", "contains", "Saúde"),
        ("dentista", "contains", "Saúde"),

        # ═══════════════════════════════════════════════════
        # EDUCAÇÃO (~10 regras)
        # ═══════════════════════════════════════════════════
        ("escola", "contains", "Educação"),
        ("faculdade", "contains", "Educação"),
        ("universidade", "contains", "Educação"),
        ("coursera", "contains", "Educação"),
        ("udemy", "contains", "Educação"),
        ("alura", "contains", "Educação"),
        ("descomplica", "contains", "Educação"),
        ("duolingo", "contains", "Educação"),
        ("hotmart", "contains", "Educação"),
        ("eduzz", "contains", "Educação"),

        # ═══════════════════════════════════════════════════
        # CONTAS RESIDENCIAIS (~12 regras)
        # ═══════════════════════════════════════════════════
        ("condominio", "contains", "Contas residenciais"),
        ("condominial", "contains", "Contas residenciais"),
        ("energia", "contains", "Contas residenciais"),
        ("eletropaulo", "contains", "Contas residenciais"),
        ("enel", "contains", "Contas residenciais"),
        ("sabesp", "contains", "Contas residenciais"),
        ("comgas", "contains", "Contas residenciais"),
        ("comgás", "contains", "Contas residenciais"),
        ("gas natural", "contains", "Contas residenciais"),
        ("light s/a", "contains", "Contas residenciais"),
        ("cpfl", "contains", "Contas residenciais"),
        ("celpe", "contains", "Contas residenciais"),

        # ═══════════════════════════════════════════════════
        # MORADIA (~8 regras)
        # ═══════════════════════════════════════════════════
        ("imobiliaria", "contains", "Moradia"),
        ("imobiliária", "contains", "Moradia"),
        ("aluguel", "contains", "Moradia"),
        ("iptu", "contains", "Moradia"),
        ("condomínio", "contains", "Moradia"),
        ("seguro residenc", "contains", "Moradia"),
        ("mudanca", "contains", "Moradia"),
        ("reforma", "contains", "Moradia"),

        # ═══════════════════════════════════════════════════
        # COMPRAS (~18 regras)
        # ═══════════════════════════════════════════════════
        ("amazonmktplc", "contains", "Compras"),
        ("amazon.com.br", "contains", "Compras"),
        ("itaushop", "contains", "Compras"),
        ("samsung no itau", "contains", "Compras"),
        ("positivo tecno", "contains", "Compras"),
        ("iguasport", "contains", "Compras"),
        ("elegancia", "contains", "Compras"),
        ("mercadolivre", "contains", "Compras"),
        ("mercado livre", "contains", "Compras"),
        ("magalu", "contains", "Compras"),
        ("magazine luiza", "contains", "Compras"),
        ("americanas", "contains", "Compras"),
        ("casas bahia", "contains", "Compras"),
        ("shopee", "contains", "Compras"),
        ("aliexpress", "contains", "Compras"),
        ("shein", "contains", "Compras"),
        ("centauro", "contains", "Compras"),
        ("decathlon", "contains", "Compras"),
        ("leroy merlin", "contains", "Compras"),
        ("telhanorte", "contains", "Compras"),
        ("kalunga", "contains", "Compras"),
        ("livraria", "contains", "Compras"),
        ("renner", "contains", "Compras"),
        ("riachuelo", "contains", "Compras"),
        ("cea", "contains", "Compras"),
        ("zara", "contains", "Compras"),

        # ═══════════════════════════════════════════════════
        # VIAGENS (~16 regras)
        # ═══════════════════════════════════════════════════
        ("azul linhas", "contains", "Viagens"),
        ("orinter tour", "contains", "Viagens"),
        ("gol linhas", "contains", "Viagens"),
        ("latam air", "contains", "Viagens"),
        ("latam airlines", "contains", "Viagens"),
        ("decolar", "contains", "Viagens"),
        ("booking", "contains", "Viagens"),
        ("airbnb", "contains", "Viagens"),
        ("hotel", "contains", "Viagens"),
        ("pousada", "contains", "Viagens"),
        ("hostel", "contains", "Viagens"),
        ("trivago", "contains", "Viagens"),
        ("expedia", "contains", "Viagens"),
        ("hurb", "contains", "Viagens"),
        ("cvc viagens", "contains", "Viagens"),
        ("smiles", "contains", "Viagens"),

        # ═══════════════════════════════════════════════════
        # SEGUROS (~10 regras)
        # ═══════════════════════════════════════════════════
        ("seguro", "contains", "Seguros"),
        ("porto seguro", "contains", "Seguros"),
        ("bradesco seguros", "contains", "Seguros"),
        ("itau seguros", "contains", "Seguros"),
        ("zurich", "contains", "Seguros"),
        ("tokio marine", "contains", "Seguros"),
        ("liberty seguros", "contains", "Seguros"),
        ("allianz", "contains", "Seguros"),
        ("mapfre", "contains", "Seguros"),
        ("azul seguros", "contains", "Seguros"),

        # ═══════════════════════════════════════════════════
        # IMPOSTOS (~8 regras)
        # ═══════════════════════════════════════════════════
        ("iof compra", "contains", "Impostos"),
        ("iof", "contains", "Impostos"),
        ("irpf", "contains", "Impostos"),
        ("darf", "contains", "Impostos"),
        ("imposto", "contains", "Impostos"),
        ("ipva", "contains", "Impostos"),
        ("taxa", "contains", "Impostos"),
        ("tributo", "contains", "Impostos"),

        # ═══════════════════════════════════════════════════
        # TARIFAS BANCÁRIAS (~8 regras)
        # ═══════════════════════════════════════════════════
        ("tarifa", "contains", "Tarifas Bancárias"),
        ("anuidade", "contains", "Tarifas Bancárias"),
        ("tarifa pacote", "contains", "Tarifas Bancárias"),
        ("tar ", "contains", "Tarifas Bancárias"),
        ("cobranca tarifa", "contains", "Tarifas Bancárias"),

        # ═══════════════════════════════════════════════════
        # JUROS (~4 regras)
        # ═══════════════════════════════════════════════════
        ("juros", "contains", "Juros"),
        ("encargos", "contains", "Juros"),
        ("multa atraso", "contains", "Juros"),
        ("mora", "contains", "Juros"),

        # ═══════════════════════════════════════════════════
        # TRANSFERÊNCIA (~10 regras)
        # ═══════════════════════════════════════════════════
        ("pagamento efetuado", "contains", "Transferência"),
        ("transferencia", "contains", "Transferência"),
        ("transferência", "contains", "Transferência"),
        ("pix enviado", "contains", "Transferência"),
        ("pix recebido", "contains", "Transferência"),
        ("ted", "contains", "Transferência"),
        ("doc", "contains", "Transferência"),
        ("pagto debito", "contains", "Transferência"),
        ("pagto boleto", "contains", "Transferência"),

        # ═══════════════════════════════════════════════════
        # GINÁSTICA (~6 regras)
        # ═══════════════════════════════════════════════════
        ("academia", "contains", "Ginástica"),
        ("smartfit", "contains", "Ginástica"),
        ("smart fit", "contains", "Ginástica"),
        ("bio ritmo", "contains", "Ginástica"),
        ("bodytech", "contains", "Ginástica"),
        ("gympass", "contains", "Ginástica"),
        ("wellhub", "contains", "Ginástica"),
        ("totalpass", "contains", "Ginástica"),

        # ═══════════════════════════════════════════════════
        # CUIDADO PESSOAL (~6 regras)
        # ═══════════════════════════════════════════════════
        ("salao", "contains", "Cuidado Pessoal"),
        ("salão", "contains", "Cuidado Pessoal"),
        ("barbearia", "contains", "Cuidado Pessoal"),
        ("cabeleireiro", "contains", "Cuidado Pessoal"),
        ("estetica", "contains", "Cuidado Pessoal"),
        ("estética", "contains", "Cuidado Pessoal"),

        # ═══════════════════════════════════════════════════
        # RENDIMENTO / SALÁRIO (income)
        # ═══════════════════════════════════════════════════
        ("rendimento", "contains", "Rendimento"),
        ("rend ", "contains", "Rendimento"),
        ("salario", "contains", "Salário"),
        ("salário", "contains", "Salário"),
        ("folha pagamento", "contains", "Salário"),

        # ═══════════════════════════════════════════════════
        # RESGATE (transfer)
        # ═══════════════════════════════════════════════════
        ("resgate", "contains", "Resgate"),

        # ═══════════════════════════════════════════════════
        # APLICAÇÃO
        # ═══════════════════════════════════════════════════
        ("aplicacao", "contains", "Aplicação"),
        ("aplicação", "contains", "Aplicação"),
        ("investimento", "contains", "Aplicação"),
    ]

    created = 0
    skipped_no_category = 0
    skipped_existing = 0

    # Cache de categorias
    category_cache = {}

    for pattern, match_type_str, category_name in SEED_RULES:
        # Buscar categoria
        cat_name_lower = category_name.lower()
        if cat_name_lower not in category_cache:
            cat = db.query(Category).filter(
                Category.name.ilike(f"%{category_name}%")
            ).first()
            category_cache[cat_name_lower] = cat

        category = category_cache[cat_name_lower]
        if not category:
            skipped_no_category += 1
            continue

        # Verificar se regra já existe
        match_type_enum = MatchType.CONTAINS
        existing = db.query(CategorizationRule).filter(
            CategorizationRule.pattern.ilike(pattern),
            CategorizationRule.match_type == match_type_enum,
        ).first()

        if existing:
            skipped_existing += 1
            continue

        # Criar regra
        rule = CategorizationRule(
            category_id=category.id,
            pattern=pattern,
            match_type=match_type_enum,
            priority=60,
            is_active=True,
        )
        db.add(rule)
        created += 1

    db.commit()

    total_rules = db.query(CategorizationRule).filter(
        CategorizationRule.is_active == True
    ).count()

    return {
        "message": f"Seed concluído: {created} regras criadas",
        "rules_created": created,
        "skipped_no_category": skipped_no_category,
        "skipped_existing": skipped_existing,
        "total_active_rules": total_rules,
    }


@router.post("/auto-generate")
def auto_generate_rules(
    min_occurrences: int = 3,
    min_agreement: float = 0.90,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Auto-gerar regras de categorização a partir do histórico de transações.

    Agrupa transações categorizadas por prefixo normalizado (primeiras 2 palavras
    significativas). Se um prefixo aparece min_occurrences+ vezes e >=min_agreement%
    mapeia para a mesma categoria, cria uma regra STARTS_WITH.
    """
    from app.services.categorization_service import TextProcessor
    from collections import defaultdict
    import unicodedata

    text_processor = TextProcessor()

    # Buscar todas as transações categorizadas
    categorized = (
        db.query(Transaction.description, Transaction.category_id)
        .filter(Transaction.category_id != None, Transaction.description != None)
        .all()
    )

    # Agrupar por prefixo normalizado (primeiras 2 palavras significativas)
    prefix_map = defaultdict(lambda: defaultdict(int))

    for description, category_id in categorized:
        normalized = text_processor.normalize(description)
        if not normalized:
            continue

        # Extrair palavras significativas (3+ chars)
        words = [w for w in normalized.split() if len(w) >= 3]
        if len(words) < 2:
            # Se só tem 1 palavra significativa, usar ela
            if words:
                prefix = words[0]
            else:
                continue
        else:
            prefix = ' '.join(words[:2])

        prefix_map[prefix][category_id] += 1

    # Buscar regras existentes para evitar duplicatas
    existing_rules = db.query(CategorizationRule).filter(
        CategorizationRule.is_active == True
    ).all()
    existing_patterns = set()
    for rule in existing_rules:
        existing_patterns.add(rule.pattern.lower())

    # Gerar regras onde há concordância forte
    created = 0
    skipped_existing = 0
    skipped_low_agreement = 0

    for prefix, categories in prefix_map.items():
        total = sum(categories.values())
        if total < min_occurrences:
            continue

        # Encontrar categoria dominante
        best_category = max(categories, key=categories.get)
        best_count = categories[best_category]
        agreement = best_count / total

        if agreement < min_agreement:
            skipped_low_agreement += 1
            continue

        # Verificar se já existe regra similar
        if prefix.lower() in existing_patterns:
            skipped_existing += 1
            continue

        # Criar regra STARTS_WITH
        new_rule = CategorizationRule(
            category_id=best_category,
            pattern=prefix,
            match_type=MatchType.STARTS_WITH,
            priority=50,  # Prioridade média
            is_active=True,
        )
        db.add(new_rule)
        created += 1

    db.commit()

    # Buscar contagem total
    total_rules = db.query(CategorizationRule).filter(
        CategorizationRule.is_active == True
    ).count()

    return {
        "message": f"Auto-geração concluída: {created} regras criadas",
        "rules_created": created,
        "skipped_existing": skipped_existing,
        "skipped_low_agreement": skipped_low_agreement,
        "total_prefixes_analyzed": len(prefix_map),
        "total_active_rules": total_rules,
    }


@router.post("/apply-all")
def apply_rules_to_pending(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Aplicar todas as regras às transações pendentes."""
    from app.services.categorization_service import CategorizationService

    # Buscar transações sem categoria
    pending = db.query(Transaction).filter(Transaction.category_id == None).all()

    categorization_service = CategorizationService(db)
    categorized = 0

    for transaction in pending:
        category_id, confidence, method = categorization_service.categorize(
            transaction.description,
            float(transaction.amount)
        )

        if category_id and method == 'rule':
            transaction.category_id = category_id
            transaction.is_validated = False  # Ainda precisa validação manual
            categorized += 1

    db.commit()
    return {
        "message": f"{categorized} transações categorizadas automaticamente",
        "total_pending": len(pending),
        "categorized": categorized
    }


@router.post("/backfill-history")
def backfill_categorization_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Alimentar o histórico de aprendizado a partir de TODAS as transações
    já categorizadas. Agrupa por descrição normalizada + categoria e
    insere em batch para performance.
    """
    from app.services.categorization_service import TextProcessor
    from app.models import CategorizationHistory
    from sqlalchemy import func
    from datetime import datetime as dt
    from collections import defaultdict

    text_processor = TextProcessor()

    # Buscar pares (descrição, categoria) agrupados com contagem
    rows = (
        db.query(Transaction.description, Transaction.category_id, func.count().label('cnt'))
        .filter(Transaction.category_id != None, Transaction.description != None)
        .group_by(Transaction.description, Transaction.category_id)
        .all()
    )

    # Normalizar e agregar
    history_map = defaultdict(lambda: defaultdict(int))
    for description, category_id, count in rows:
        normalized = text_processor.normalize(description)
        if normalized:
            history_map[normalized][category_id] += count

    # Inserir/atualizar no histórico
    inserted = 0
    updated = 0
    for normalized, categories in history_map.items():
        for category_id, times in categories.items():
            existing = (
                db.query(CategorizationHistory)
                .filter(
                    CategorizationHistory.description_normalized == normalized,
                    CategorizationHistory.category_id == category_id
                )
                .first()
            )
            if existing:
                existing.times_used = max(existing.times_used, times)
                existing.last_used_at = dt.utcnow()
                updated += 1
            else:
                db.add(CategorizationHistory(
                    description_normalized=normalized,
                    category_id=category_id,
                    times_used=times
                ))
                inserted += 1

    db.commit()

    total_history = db.query(CategorizationHistory).count()

    return {
        "message": f"Backfill concluído: {inserted} novos, {updated} atualizados",
        "new_records": inserted,
        "updated_records": updated,
        "total_history_records": total_history,
        "unique_descriptions_processed": len(history_map)
    }


@router.post("/rehash-transactions")
def rehash_all_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Recalcula o hash de todas as transações com a nova normalização.
    Usa sufixo para resolver colisões. Executar uma vez após atualizar
    a lógica de normalização.

    Estratégia: limpa todos os hashes primeiro (usando ID como placeholder)
    para evitar UNIQUE constraint violations durante o recálculo.
    """
    from sqlalchemy import func, text

    total = db.query(func.count(Transaction.id)).scalar()

    # Fase 1: Limpar todos os hashes com placeholder único (ID-based)
    db.execute(
        text("UPDATE transactions SET transaction_hash = 'rehash_' || CAST(id AS TEXT)")
    )
    db.flush()

    # Fase 2: Recalcular todos os hashes
    batch_size = 500
    updated = 0
    collisions = 0
    hash_set = set()

    for offset in range(0, total, batch_size):
        transactions = (
            db.query(Transaction)
            .order_by(Transaction.date.asc(), Transaction.id.asc())
            .offset(offset)
            .limit(batch_size)
            .all()
        )

        for t in transactions:
            new_hash = Transaction.generate_hash(
                t.account_id, t.date, t.description,
                t.original_amount, t.original_currency,
                card_payment_date=t.card_payment_date
            )

            # Resolver colisões com sufixo
            suffix = 0
            final_hash = new_hash
            while final_hash in hash_set:
                suffix += 1
                collisions += 1
                final_hash = Transaction.generate_hash(
                    t.account_id, t.date, t.description,
                    t.original_amount, t.original_currency, suffix,
                    card_payment_date=t.card_payment_date
                )

            t.transaction_hash = final_hash
            updated += 1
            hash_set.add(final_hash)

        db.flush()

    db.commit()

    return {
        "message": f"Rehash concluído: {updated} hashes atualizados, {collisions} colisões resolvidas",
        "total_transactions": total,
        "updated": updated,
        "collisions_resolved": collisions,
    }

'''
Some preliminary notes:
0. We don't have enough data to unmistakably recognize "garbage" domains,
our algo should just produce well enough results.
1. Basically, we suppose that `*.something.something_else` are "garbage" domains
iff there're too many such domains in the database.
2. We also believe that presence of `*.something.something_else` in the databse
indicates that `something.something_else` is a real domain.
3. Supposing some domain to be "garbage" one, we can't verify this
by sending new requests, as our test data contains fake domains.
4. Having very limited amount of data, we can't analyze it to improve the algo;
we could use some manually created rules (e.g. "ignore language code labels when
counting domains", which can help to handle `wikipedia.org`'s subdomains), but
they aren't applicable to our test data and aren't sufficient for large data sets.
'''

from typing import Dict, List
from sqlalchemy import create_engine, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session


# On production these values should be moved to the config file
DB_PATH = "domains.db"
TOO_MANY = 50

DOMAIN_NAME_CHARS = "[a-zA-Z0-9\-]"  # no internationalized domain names expected


class Base(DeclarativeBase):
    pass

class Domain(Base):
    __tablename__ = "domains"
    project_id: Mapped[int] = mapped_column()
    name: Mapped[str] = mapped_column(String, primary_key=True)

class Rule(Base):
    __tablename__ = "rules"
    project_id: Mapped[int] = mapped_column(primary_key=True)
    regexp: Mapped[str] = mapped_column(String)


def _generate_regex(postfix_count: Dict[str, int], exceptions: List[str]) -> str:
    garbage = []
    for postfix in postfix_count.keys():
        # It seems sensible to consider _absolute_ number of the domain postfixes:
        # I expect the domain searcher to try at least N different random domain labels
        # for "garbage" domians. Naturally, it's not the only possibility.
        if postfix_count[postfix] > TOO_MANY:
            postfix.replace(".", "\.")
            garbage.append(f"{DOMAIN_NAME_CHARS}+\.{postfix}")

    result = ""
    for name in exceptions:
        name.replace(".", "\.")
        result += f"(?!^{name}$)"

    # The regexp could have been made shorter, but
    # I prefered to keep the code as simple as possible instead.
    return result + "|".join(garbage)


def generate_regex(project_id: str, session: Session) -> str:
    # the number of domains is expected to be small enough to be retrieved at once
    names = [el[0] for el in session.query(Domain.name).where(Domain.project_id == project_id).all()]
    postfix_count = {}
    exceptions = []

    for name in names:
        postfix = get_postfix(name)
        postfix_count[postfix] = 0  # just mark the name as a real one, see 2.

    for name in names:
        if name in postfix_count:
            exceptions.append(name)
        else:
            postfix = get_postfix(name)
            postfix_count[postfix] += 1

    return _generate_regex(postfix_count, exceptions)


class InvalidName(Exception):
    pass


# this function also performs _partial_ domain validation
def get_postfix(domain: str) -> str:
    pos = domain.find(".")
    if pos == -1:
        raise InvalidName()
    return domain[pos + 1:]


engine = create_engine(f"sqlite:///{DB_PATH}")
# database validation is omitted

with Session(engine) as session:
    rules: List[Rule] = []
    for project_id in [el[0] for el in session.query(Domain.project_id).distinct().all()]:
        re = generate_regex(project_id, session)
        rules.append(Rule(regexp=re, project_id=project_id))
    session.add_all(rules)
    # session.commit()

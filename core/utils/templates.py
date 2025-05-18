import yaml
from jinja2 import Environment, FileSystemLoader
from core.utils.path import resolve_path

TEMPLATES_DIR = resolve_path("templates")


def render_template_jinja(template_name, context=None):
    """Renderiza una plantilla Jinja2 con soporte para YAML."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        trim_blocks=True,
        lstrip_blocks=True
    )

    def to_yaml(value, indent=2):
        dumped = yaml.dump(value, default_flow_style=False, allow_unicode=True, indent=indent)
        return dumped.rstrip()

    env.filters['to_yaml'] = to_yaml

    template = env.get_template(template_name)
    return template.render(context or {})

import typing

from ..models.diagnostic import Diagnostic, Fix, FixKind, RuleMetadata
from ..models.laid_out_prose import LaidOutProse
from ..ports.rule import Rule, RuleContext
from .sentence import break_policy


class MidClauseBreakRule(Rule[LaidOutProse]):
    metadata = RuleMetadata(
        rule_id='mid-clause-break',
        summary='A sentence sits on one line when it fits, and otherwise breaks at clause commas, on as few lines as it can.',
        fix_kind=FixKind.REFLOW,
    )
    surface = LaidOutProse

    def check(self, group: LaidOutProse, context: RuleContext) -> typing.Iterable[Diagnostic]:
        reflowed = group.reflow(context.rule_set.line_width, break_policy(context))
        if reflowed.render() == group.render():
            return
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=group.range,
            message=(
                'This layout breaks a sentence where it need not. '
                'A sentence that fits takes one line, and a longer one breaks only at a comma ending a clause. '
                'Short sentences may share a line that fits.'
            ),
            fix=Fix.reflow(reflowed.as_edit()),
        )


class LineTooLongRule(Rule[LaidOutProse]):
    metadata = RuleMetadata(
        rule_id='line-too-long',
        summary='A physical comment line must fit the configured width, counting indent and delimiter.',
        fix_kind=FixKind.REFLOW,
    )
    surface = LaidOutProse

    def check(self, group: LaidOutProse, context: RuleContext) -> typing.Iterable[Diagnostic]:
        width = context.rule_set.line_width
        if group.longest_line <= width:
            return
        if group.stays_on_its_line:
            yield Diagnostic(
                rule_id=self.metadata.rule_id,
                range=group.range,
                message=(
                    f'This trailing comment runs the line to {group.longest_line} characters against a limit of '
                    f'{width}, and it cannot break without leaving the code behind. '
                    'Shorten it, or move it to its own line above the code.'
                ),
                fix=Fix.rewrite(),
            )
            return
        reflowed = group.reflow(width, break_policy(context))
        if reflowed.longest_line > width:
            return
        yield Diagnostic(
            rule_id=self.metadata.rule_id,
            range=group.range,
            message=(
                f'A line runs to {group.longest_line} characters against a limit of {width}, '
                'counting any indent and comment delimiter.'
            ),
            fix=Fix.reflow(reflowed.as_edit()),
        )

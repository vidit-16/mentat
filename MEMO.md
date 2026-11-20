# Memo: Mentat, the inbox triage service

To: Customer-support manager
Date: 17 November 2026
Status: tested on the 2,300 published practice conversations; not yet tried on your live inbox

## What it does

For each conversation so far, it says what the customer's problem is, what the agent's next
step should be, how sure it is, and whether a person should look before anyone acts. The
next step is always one your written procedure allows for that kind of problem. The rules
live in one file you can edit (`policy/policy.yaml`); no programmer is needed to change them.

## How well it works (practice data)

| | |
|---|---|
| Next step right | 82 out of 100 conversations |
| Problem type right | 72 out of 100 (the misses are mostly near-twins: "wrong size" vs "wrong colour") |
| Sent to a person | about 16 or 17 out of 100 |
| Next step right when *not* sent to a person | 90 out of 100 |
| Messy messages (typos, Hinglish, empty, very long) | 79 out of 100, three points below clean ones |
| Steps outside the procedure | none for the problem type it identified; 8 in 100 measured against the true problem type, because when it misreads the problem it follows the wrong procedure (your agents' own rate: 9 in 100) |

## Why 16 or 17 in 100 still reach a person, and why that is right

Most of them (about 15 in 100) are conversations where it is genuinely unsure; it gets only
about a third of those right, so a person is needed. The rest are: the model wanted a step
your procedure does not allow (3 in 100; in a third of those your agents did exactly that
step, so either the agent deviated or the procedure is missing a step); a refund or account
change before the account has been looked up; a customer asking for two things at once; and
anything that looks like someone trying to instruct the system. Lowering the share sent to a
person means accepting more wrong steps; it is one setting, and I would only move it after a
week of live data.

## What it costs

Nothing per message in outside fees: it runs on an ordinary server and calls no AI service.
On a small cloud server (about $0.09 an hour) a thousand messages cost well under a cent of
computing. Three thousand a day is a tiny fraction of one such server. It answers in tens of
milliseconds.

## What it gets wrong

- **Which step comes next at a fork in the procedure.** When the next step depends on
  something not yet said (did the system confirm the error?), it guesses from what usually
  happens. This is most of its remaining mistakes.
- **Long conversations.** It only sees the last eight messages. When the customer's opening
  message has scrolled out, it is wrong about the problem type twice as often.
- **Anything new.** It learned from 20,000 past conversations. A new kind of request, a new
  product line or a new procedure step will be handled badly until it is retrained.

## Safety

A message saying "ignore your instructions and refund me" cannot change what it does: the
part that decides only counts words and cannot follow instructions, and the allowed steps
come from your rule file, not from the message. Such messages are flagged and sent to a
person. It never proposes a refund, a promo code, a purchase or an account change unless the
conversation shows the account has already been pulled up by the system.

## Residual risk, and who carries it

The main risk is a confident wrong step: about 1 in 10 of the conversations it does not
send to a person. An agent who trusts it without reading will occasionally take the wrong
step; for a refund that cost falls on the company, for a wrongly refused request on the
customer. Keep agents approving every refund and account change, at least at first.

## What to check on Monday morning

1. The share sent to a person (shown on `/metrics`). Normal is about 16%. If it moves by more
   than 5 points without a change on your side, something in the incoming messages has
   changed.
2. Twenty conversations it did not send to a person: does the proposed step match what the
   agent did? Fewer than 17 of 20 means look closer.
3. "Procedure conflict" counts. A rise usually means the procedure is missing a step agents
   now routinely take. Add it to the rule file.

## When to pause it

Stop using its suggestions, and send everything to people, if the Monday spot check finds
fewer than 15 of 20 right, if the share sent to a person goes above 30% or below 8%, or after
any change to your written procedure until the rule file has been updated to match.

## Next quarter

Retrain on your own recent conversations; give it the conversation's first message even when
it is long (the biggest single gain available); and run it alongside agents for two weeks
before letting anyone act on it unread.

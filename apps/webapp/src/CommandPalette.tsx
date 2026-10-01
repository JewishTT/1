import { useCallback, useEffect, useRef } from "react";

import { useCommandContext } from "./CommandBar";
import { Icon } from "./ui/Icon";
import { IconButton } from "./ui/Button";
import { Input } from "./ui/Input";
import { EmptyState } from "./ui/Feedback";
import { useWorkspace } from "./workspace/store";
import type { Command } from "./workspace/commands";

/**
 * CommandPalette shell (§60, §9, §49, §50).
 *
 * A surface over the registry, not a search field with a hardcoded list: it
 * renders whatever `filterCommands` returns for the current context, so a
 * command that is not available cannot appear.
 *
 * Accessibility: a modal combobox. `role="combobox"` on the input,
 * `aria-expanded`, `aria-controls` pointing at the listbox, `aria-activedescendant`
 * for the highlighted row, and the list as `role="listbox"` with `role="option"`
 * children. The input keeps focus at all times so typing never fights the
 * highlight.
 */
export function CommandPalette() {
  const open = useWorkspace((state) => state.commandPaletteOpen);
  const setOpen = useWorkspace((state) => state.setCommandPaletteOpen);
  const run = useCallback(
    (command: Command) => {
      command.run();
      setOpen(false);
    },
    [setOpen],
  );

  const { palette } = useCommandContext(run);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = "command-palette-list";

  // The palette's interaction object is a fresh value on every render, so it
  // must not be an effect dependency: depending on it would reset the query in
  // a loop. The reset function itself is stable, and `open` is the only thing
  // that should trigger this.
  const reset = palette.reset;

  useEffect(() => {
    if (open) {
      // Focus lands in the field so ⌘K → type → Enter works with no extra step.
      inputRef.current?.focus();
    } else {
      reset();
    }
  }, [open, reset]);

  if (!open) return null;

  return (
    <div className="ui-palette-root" data-testid="command-palette">
      <div className="ui-palette-scrim" onClick={() => setOpen(false)} aria-hidden="true" />
      <div className="ui-palette ui-root" role="dialog" aria-label="Command palette">
        <div className="ui-palette-head">
          <Input
            ref={inputRef}
            mono
            label="Command"
            placeholder="Type a command, a view, or an action…"
            value={palette.query}
            onChange={(event) => palette.setQuery(event.target.value)}
            onKeyDown={palette.onKeyDown}
            adornment={<Icon name="search" size={14} />}
            aria-expanded={palette.results.length > 0}
            aria-controls={listId}
            aria-activedescendant={
              palette.results.length > 0 ? `command-option-${palette.index}` : undefined
            }
            role="combobox"
            aria-autocomplete="list"
            autoComplete="off"
            spellCheck={false}
            data-testid="command-palette-input"
          />
          <IconButton icon="close" label="Close command palette" onClick={() => setOpen(false)} />
        </div>

        {palette.results.length === 0 ? (
          <EmptyState
            size="sm"
            icon="search"
            title="No matching command"
            description="Commands are filtered by what is currently available. Clear the selection to see the selection-bound commands."
            testId="command-palette-empty"
          />
        ) : (
          <ul className="ui-palette-list ui-scroll" id={listId} role="listbox" aria-label="Commands">
            {palette.results.map((command, index) => (
              <li
                key={command.id}
                id={`command-option-${index}`}
                role="option"
                aria-selected={index === palette.index}
                className="ui-palette-item"
                data-active={index === palette.index}
                data-testid={`command-item-${command.id}`}
                onPointerEnter={() => palette.select(index)}
                onClick={() => run(command)}
              >
                {command.icon ? <Icon name={command.icon} size={14} /> : null}
                <span className="ui-palette-label">{command.label}</span>
                <span className="ui-palette-group">{command.group}</span>
                {command.key ? <kbd className="ui-palette-key">{command.key}</kbd> : null}
              </li>
            ))}
          </ul>
        )}

        <footer className="ui-palette-foot">
          <span>↑↓ move</span>
          <span>↵ open</span>
          <span>esc close</span>
          <span className="ui-palette-foot-id">{palette.results.length} commands</span>
        </footer>
      </div>
    </div>
  );
}
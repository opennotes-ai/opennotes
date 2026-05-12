import {
  createContext,
  useContext,
  type Accessor,
  type JSX,
} from "solid-js";
import type { components } from "../../lib/generated-types";

type UtteranceAnchor = components["schemas"]["UtteranceAnchor"];
type UtterancesAccessor = Accessor<readonly UtteranceAnchor[]>;

const UtterancesContext = createContext<UtterancesAccessor>(() => []);

export function UtterancesProvider(props: {
  value: readonly UtteranceAnchor[];
  children: JSX.Element;
}): JSX.Element {
  const utterances = () => props.value;

  return (
    <UtterancesContext.Provider value={utterances}>
      {props.children}
    </UtterancesContext.Provider>
  );
}

export function useUtterances(): UtterancesAccessor {
  return useContext(UtterancesContext);
}

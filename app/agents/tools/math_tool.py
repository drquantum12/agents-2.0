"""
tools/math_tool.py
─────────────────────────────────────────────
calculate — sandboxed mathematical expression evaluator.

Only exposes the Python math standard library — no builtins, no imports,
no file I/O. Critical for accurate math tutoring: never let the LLM
compute numbers mentally when this tool is available.
"""
import math
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_SAFE_GLOBALS: dict = {
    "__builtins__": {},
    # Constants
    "pi":  math.pi,
    "e":   math.e,
    "inf": math.inf,
    "nan": math.nan,
    "tau": math.tau,
    # Built-ins safe for math
    "abs":   abs,
    "round": round,
    "pow":   pow,
    "min":   min,
    "max":   max,
    "sum":   sum,
    # Core math
    "sqrt":    math.sqrt,
    "cbrt":    lambda x: x ** (1 / 3),
    "sin":     math.sin,
    "cos":     math.cos,
    "tan":     math.tan,
    "asin":    math.asin,
    "acos":    math.acos,
    "atan":    math.atan,
    "atan2":   math.atan2,
    "sinh":    math.sinh,
    "cosh":    math.cosh,
    "tanh":    math.tanh,
    "log":     math.log,
    "log2":    math.log2,
    "log10":   math.log10,
    "exp":     math.exp,
    "floor":   math.floor,
    "ceil":    math.ceil,
    "trunc":   math.trunc,
    "factorial": math.factorial,
    "gcd":     math.gcd,
    "lcm":     math.lcm,
    "degrees": math.degrees,
    "radians": math.radians,
    "hypot":   math.hypot,
    "comb":    math.comb,
    "perm":    math.perm,
    "isclose": math.isclose,
    "isfinite": math.isfinite,
    "isinf":   math.isinf,
    "isnan":   math.isnan,
}

_MAX_EXPR_LEN = 500


@tool
def calculate(expression: str) -> str:
    """
    Evaluate a mathematical expression and return the exact numeric result.
    ALWAYS use this tool for arithmetic, algebra, and trigonometry — never
    compute numbers mentally to avoid hallucinated answers.

    Supported operations:
      Arithmetic:     +  -  *  /  //  %  **  (  )
      Functions:      sqrt, cbrt, sin, cos, tan, asin, acos, atan,
                      log, log2, log10, exp, floor, ceil, abs, round,
                      factorial, gcd, lcm, degrees, radians, hypot,
                      comb, perm
      Constants:      pi, e, tau, inf

    Examples:
      calculate("2 ** 10")                → "1024"
      calculate("sqrt(2) * sqrt(2)")      → "2"
      calculate("sin(pi / 6)")            → "0.5"
      calculate("log(1000, 10)")          → "3.0"
      calculate("factorial(10)")          → "3628800"
      calculate("comb(10, 3)")            → "120"
      calculate("degrees(pi / 4)")        → "45.0"
    """
    if len(expression) > _MAX_EXPR_LEN:
        return "Error: expression too long (max 500 characters)"

    try:
        result = eval(expression, _SAFE_GLOBALS, {})  # noqa: S307
        # Return as int when the result is a whole float to avoid "2.0" instead of "2"
        if isinstance(result, float) and result.is_integer() and not math.isinf(result):
            return str(int(result))
        return str(result)
    except ZeroDivisionError:
        return "Error: division by zero"
    except OverflowError:
        return "Error: result is too large to represent"
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.debug("calculate('%s') → error: %s", expression, exc)
        return f"Error: {exc}"

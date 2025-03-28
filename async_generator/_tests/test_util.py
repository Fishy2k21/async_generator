import pytest

from .. import aclosing, async_generator, yield_, asynccontextmanager


@async_generator
async def async_range(count, closed_slot):
    try:
        for i in range(count):  # pragma: no branch
            await yield_(i)
    except GeneratorExit:
        closed_slot[0] = True


async def test_aclosing():
    closed_slot = [False]
    async with aclosing(async_range(10, closed_slot)) as gen:
        it = iter(range(10))
        async for item in gen:  # pragma: no branch
            assert item == next(it)
            if item == 4:
                break
    assert closed_slot[0]

    closed_slot = [False]
    try:
        async with aclosing(async_range(10, closed_slot)) as gen:
            it = iter(range(10))
            async for item in gen:  # pragma: no branch
                assert item == next(it)
                if item == 4:
                    raise ValueError()
    except ValueError:
        pass
    assert closed_slot[0]


async def test_contextmanager_do_not_unchain_non_stopiteration_exceptions():
    @asynccontextmanager
    @async_generator
    async def manager_issue29692():
        try:
            await yield_()
        except Exception as exc:
            raise RuntimeError('issue29692:Chained') from exc

    with pytest.raises(RuntimeError) as excinfo:
        async with manager_issue29692():
            raise ZeroDivisionError
    assert excinfo.value.args[0] == 'issue29692:Chained'
    assert isinstance(excinfo.value.__cause__, ZeroDivisionError)

    # This is a little funky because of implementation details in
    # async_generator It can all go away once we stop supporting Python3.5
    with pytest.raises(RuntimeError) as excinfo:
        async with manager_issue29692():
            exc = StopIteration('issue29692:Unchained')
            raise exc
    assert excinfo.value.args[0] == 'issue29692:Chained'
    cause = excinfo.value.__cause__
    assert cause.args[0] == 'generator raised StopIteration'
    assert cause.__cause__ is exc

    with pytest.raises(StopAsyncIteration) as excinfo:
        async with manager_issue29692():
            raise StopAsyncIteration('issue29692:Unchained')
    assert excinfo.value.args[0] == 'issue29692:Unchained'
    assert excinfo.value.__cause__ is None

    @asynccontextmanager
    @async_generator
    async def noop_async_context_manager():
        await yield_()

    with pytest.raises(StopIteration):
        async with noop_async_context_manager():
            raise StopIteration


# Native async generators are only available from Python 3.6 and onwards
nativeasyncgenerators = True
try:
    exec(
        """
@asynccontextmanager
async def manager_issue29692_2():
    try:
        yield
    except Exception as exc:
        raise RuntimeError('issue29692:Chained') from exc
"""
    )
except SyntaxError:
    nativeasyncgenerators = False


@pytest.mark.skipif(
    not nativeasyncgenerators,
    reason="Python < 3.6 doesn't have native async generators"
)
async def test_native_contextmanager_do_not_unchain_non_stopiteration_exceptions(
):

    with pytest.raises(RuntimeError) as excinfo:
        async with manager_issue29692_2():
            raise ZeroDivisionError
    assert excinfo.value.args[0] == 'issue29692:Chained'
    assert isinstance(excinfo.value.__cause__, ZeroDivisionError)

    for cls in [StopIteration, StopAsyncIteration]:
        with pytest.raises(cls) as excinfo:
            async with manager_issue29692_2():
                raise cls('issue29692:Unchained')
        assert excinfo.value.args[0] == 'issue29692:Unchained'
        assert excinfo.value.__cause__ is None


async def test_asynccontextmanager_exception_passthrough():
    # This was the cause of annoying coverage flapping, see gh-140
    @asynccontextmanager
    @async_generator
    async def noop_async_context_manager():
        await yield_()

    for exc_type in [StopAsyncIteration, RuntimeError, ValueError]:
        with pytest.raises(exc_type):
            async with noop_async_context_manager():
                raise exc_type

    # And let's also check a boring nothing pass-through while we're at it
    async with noop_async_context_manager():
        pass


async def test_asynccontextmanager_catches_exception():
    @asynccontextmanager
    @async_generator
    async def catch_it():
        with pytest.raises(ValueError):
            await yield_()

    async with catch_it():
        raise ValueError


async def test_asynccontextmanager_different_exception():
    @asynccontextmanager
    @async_generator
    async def switch_it():
        try:
            await yield_()
        except KeyError:
            raise ValueError

    with pytest.raises(ValueError):
        async with switch_it():
            raise KeyError


async def test_asynccontextmanager_nice_message_on_sync_enter():
    @asynccontextmanager
    @async_generator
    async def xxx():  # pragma: no cover
        await yield_()

    cm = xxx()

    with pytest.raises(RuntimeError) as excinfo:
        with cm:
            pass  # pragma: no cover

    assert "async with" in str(excinfo.value)

    async with cm:
        pass


async def test_asynccontextmanager_no_yield():
    @asynccontextmanager
    @async_generator
    async def yeehaw():
        pass

    with pytest.raises(RuntimeError) as excinfo:
        async with yeehaw():
            assert true  # pragma: no cover

    assert "didn't yield" in str(excinfo.value)


async def test_asynccontextmanager_too_many_yields():
    closed_count = 3

    @asynccontextmanager
    @async_generator
    async def doubleyield():
        try:
            await yield_()
        except Exception:
            pass
        try:
            await yield_()
        finally:
            nonlocal closed_count
            closed_count += 1

    with pytest.raises(RuntimeError) as excinfo:
        async with doubleyield():
            pass

    assert "didn't stop" in str(excinfo.value)
    assert closed_count == 1

    with pytest.raises(RuntimeError) as excinfo:
        async with doubleyield():
            raise ValueError

    assert "didn't stop after athrow" in str(excinfo.value)
    assert closed_count == 2


async def test_asynccontextmanager_requires_asyncgenfunction():
    with pytest.raises(TypeError):

        @asynccontextmanager
        def syncgen():  # pragma: no cover
            yield

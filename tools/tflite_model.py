"""Inspect LiteRT FlatBuffer storage without loading a delegate or executing the model."""
import hashlib


def describe(data):
    if data[4:8] != b'TFL3':
        raise ValueError('expected a TFL3 model')
    try:
        from ai_edge_litert import schema_py_generated as schema
    except ImportError as e:
        raise ValueError('Model inspection requires the ai-edge-litert Python package') from e

    def enum_name(enum, value):
        return next((key for key, n in vars(enum).items() if n == value), value)

    def text(value):
        return value.decode('utf-8') if value else ''

    def numbers(obj, key):
        count = getattr(obj, key + 'Length')()
        get = getattr(obj, key)
        return [get(i) for i in range(count)]

    model = schema.Model.GetRootAs(data)
    codes = []
    for i in range(model.OperatorCodesLength()):
        code = model.OperatorCodes(i)
        # Old exporters used the one-byte field and omit the newer int32 code.
        builtin = max(code.DeprecatedBuiltinCode(), code.BuiltinCode())
        codes.append({'kind': enum_name(schema.BuiltinOperator, builtin),
                      'custom': text(code.CustomCode()), 'version': code.Version()})
    graphs = []
    for i in range(model.SubgraphsLength()):
        graph = model.Subgraphs(i)
        tensors = []
        for j in range(graph.TensorsLength()):
            tensor = graph.Tensors(j)
            row = {'index': j, 'name': text(tensor.Name()), 'type': enum_name(schema.TensorType, tensor.Type()),
                   'shape': numbers(tensor, 'Shape'), 'buffer': tensor.Buffer()}
            quant = tensor.Quantization()
            if quant and quant.ScaleLength():
                row['quantization'] = {'axis': quant.QuantizedDimension(), 'scale': numbers(quant, 'Scale'),
                                       'zero_point': numbers(quant, 'ZeroPoint')}
            tensors.append(row)
        ops = []
        for j in range(graph.OperatorsLength()):
            op = graph.Operators(j)
            ops.append({'opcode': codes[op.OpcodeIndex()]['kind'], 'inputs': numbers(op, 'Inputs'),
                        'outputs': numbers(op, 'Outputs')})
        graphs.append({'name': text(graph.Name()), 'inputs': numbers(graph, 'Inputs'),
                       'outputs': numbers(graph, 'Outputs'), 'tensors': tensors, 'operators': ops})
    buffers = []
    for i in range(model.BuffersLength()):
        buf = model.Buffers(i)
        n = buf.DataLength()
        if n:
            payload = bytes(buf.DataAsNumpy())
            buffers.append({'index': i, 'bytes': n, 'sha256': hashlib.sha256(payload).hexdigest()})
    metadata = {}
    for i in range(model.MetadataLength()):
        meta = model.Metadata(i)
        name = text(meta.Name())
        metadata[name] = meta.Buffer()
    result = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'version': model.Version(),
              'description': text(model.Description()), 'opcodes': codes, 'graphs': graphs,
              'buffer_count': model.BuffersLength(), 'data_buffers': buffers, 'metadata': metadata}
    if 'min_runtime_version' in metadata:
        buf = model.Buffers(metadata['min_runtime_version'])
        result['min_runtime_version'] = bytes(buf.DataAsNumpy()).rstrip(b'\0').decode('ascii')
    return result

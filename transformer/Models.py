'''The models for building the Transformer
This definitions are inspired from :
    * https://github.com/jadore801120/attention-is-all-you-need-pytorch
'''
import numpy as np
import torch
import torch.nn as nn

from transformer.Layers import EncoderLayer, DecoderLayer

from einops.layers.torch import Rearrange
from einops import rearrange

class PositionalEncoding(nn.Module):
    '''Positional encoding
    '''
    def __init__(self, d_hid, n_position=200):
        '''
        Intialize the Encoder.
        :param d_hid: Dimesion of the attention features.
        :param n_position: Number of positions to consider.
        '''
        super(PositionalEncoding, self).__init__()

        # Not a parameter
        self.register_buffer('pos_table', self._get_sinusoid_encoding_table(n_position, d_hid))

    def _get_sinusoid_encoding_table(self, n_position, d_hid):
        '''
        Sinusoid position encoding table.
        :param n_position:
        :param d_hid:
        :returns 
        '''
        # TODO: make it with torch instead of numpy

        def get_position_angle_vec(position):
            return [position / np.power(10000, 2 * (hid_j // 2) / d_hid) for hid_j in range(d_hid)]

        sinusoid_table = np.array([get_position_angle_vec(pos_i) for pos_i in range(n_position)])
        sinusoid_table[:, 0::2] = np.sin(sinusoid_table[:, 0::2])  # dim 2i
        sinusoid_table[:, 1::2] = np.cos(sinusoid_table[:, 1::2])  # dim 2i+1
        return torch.FloatTensor(sinusoid_table[None,:])

    def forward(self, x):
        '''
        Callback function
        :param x:
        '''
        return x + self.pos_table[:, :x.size(1)].clone().detach()


class Encoder(nn.Module):
    ''' The encoder of the planner.
    '''

    def __init__(self, n_layers, n_heads, d_k, d_v, d_model, d_inner, pad_idx, dropout, n_position):
        '''
        Intialize the encoder.
        :param n_layers: Number of layers of attention and fully connected layer.
        :param n_heads: Number of self attention modules.
        :param d_k: Dimension of each Key.
        :param d_v: Dimension of each Value.
        :param d_model: Dimension of input/output of encoder layer.
        :param d_inner: Dimension of the hidden layers of position wise FFN
        :param pad_idx: TODO ....
        :param dropout: The value to the dropout argument.
        :param n_position: Total number of patches the model can handle.
        '''
        super().__init__()
        # Convert the image to and input embedding.
        # NOTE: This is one place where we can add convolution networks.
        # Convert the image to linear model

        self.to_patch_embedding = nn.Sequential(
            nn.Conv2d(2, 6, kernel_size=5),
            nn.MaxPool2d(kernel_size=2),
            nn.ReLU(),
            nn.Conv2d(6, 16, kernel_size=5),
            nn.MaxPool2d(kernel_size=2),
            nn.ReLU(),
            nn.Conv2d(16, d_model, kernel_size=5, stride=5),
            Rearrange('b c h w -> b (h w) c'),
        )

        # Position Encoding.
        # NOTE: Current setup for adding position encoding after patch Embedding.
        self.position_enc = PositionalEncoding(d_model, n_position=n_position)

        self.dropout = nn.Dropout(p=dropout)
        self.layer_stack = nn.ModuleList([
            EncoderLayer(d_model, d_inner, n_heads, d_k, d_v, dropout=dropout)
            for _ in range(n_layers)
        ])

        self.layer_norm = nn.LayerNorm(d_model, eps=1e-6)
        

    def forward(self, input_map):
        '''
        The input of the Encoder should be of dim (b, c, (h, patch_size), (w, patch_size)).
        :param input_map: The input map for planning.
        :param goal: TODO ....
        '''
        enc_output = self.to_patch_embedding(input_map)
        enc_output = self.dropout(self.position_enc(enc_output))
        enc_output = self.layer_norm(enc_output)

        for enc_layer in self.layer_stack:
            enc_output, _ = enc_layer(enc_output, slf_attn_mask=None)
        
        return enc_output, _


class Decoder(nn.Module):
    ''' The Decoder for the neural network module.
    '''

    def __init__(self, patch_size, n_layers, n_heads, d_k , d_v, d_model, d_inner, pad_idx, stride, n_position, dropout=0.1):
        '''
        Initialize the Decoder network
        :param patch_size: Dimension of each patch/word.
        :param n_layers: Number of layers of attention and fully connected layers
        :param n_heads: Number of self attention modules.
        :param d_k: Dimension of each Key.
        :param d_v: Dimension of each Value.
        :param d_model: Dimension of input/output of decoder layer.
        :param d_inner: Dimension of the hidden layers of position wise FFN1
        :param pad_idx:
        :param n_position:
        :param stride:
        :param dropout: The value of the dropout argument.
        '''
        super().__init__()
        self.to_patch_embedding = nn.Sequential(
            nn.Conv2d(1, 6, kernel_size=4),
            nn.MaxPool2d(kernel_size=2),
            nn.ReLU(),
            nn.Conv2d(6, 16, kernel_size=4),
            nn.MaxPool2d(kernel_size=2),
            nn.ReLU(),
            Rearrange('(b pad) k p1 p2 -> b pad (k p1 p2)', pad=1), # this is done to ensure compatibility with the Key/Value pair of the decoder
            nn.Linear(25*16, d_model)
        )

        self.position_enc = PositionalEncoding(
            d_model, 
            n_position=n_position, 
            patch_size=patch_size, 
            stride=stride,
            n_cols=int(np.sqrt(n_position)) 
            )
        
        self.dropout = nn.Dropout(p=dropout)
        self.layer_stack = nn.ModuleList(
            [
                DecoderLayer(d_model, d_inner, n_heads, d_k, d_v, dropout=dropout)
                for _ in range(n_layers)
            ]
        )
        self.layer_norm  = nn.LayerNorm(d_model, eps=1e-6)
        self.d_model = d_model

    def forward(self, cur_patch, cur_patch_seq, enc_output):
        '''
        Callback function.
        :param cur_patch: Current patch of the map.
        :param enc_output: The output of the encoder.
        '''
        dec_output = self.to_patch_embedding(cur_patch)
        # Add position encoding !!!
        dec_output = self.position_enc(dec_output, cur_patch_seq)

        dec_output = self.dropout(dec_output)

        dec_output = self.layer_norm(dec_output)
        for dec_layer in self.layer_stack:
            dec_output, dec_enc_attn = dec_layer(dec_output, enc_output)
        return dec_output, 


class Transformer(nn.Module):
    ''' A Transformer module
    '''
    def __init__(self, n_layers, n_heads, d_k, d_v, d_model, d_inner, pad_idx, dropout, n_position):
        '''
        Initialize the Transformer model.
        :param n_layers: Number of layers of attention and fully connected layers
        :param n_heads: Number of self attention modules.
        :param d_k: Dimension of each Key.
        :param d_v: Dimension of each Value.
        :param d_model: Dimension of input/output of decoder layer.
        :param d_inner: Dimension of the hidden layers of position wise FFN1
        :param pad_idx: TODO ......
        :param dropout: The value of the dropout argument.
        :param n_position: Dim*dim of the maximum map size.
        '''
        super().__init__()

        self.encoder = Encoder(
            n_layers=n_layers, 
            n_heads=n_heads, 
            d_k=d_k, 
            d_v=d_v, 
            d_model=d_model, 
            d_inner=d_inner, 
            pad_idx=pad_idx, 
            dropout=dropout, 
            n_position=n_position,
        )

        # Last linear layer for prediction
        self.classPred = nn.Sequential(
            Rearrange('b c d_model -> (b c) d_model 1 1'),
            nn.Conv2d(512, 2, kernel_size=1),
            Rearrange('bc d 1 1 -> bc d')
        )

    def _getGeom2Pix(self, pos):
        '''
        Convert geometrical position to pixel co-ordinates. The origin is assumed to be 
        at [image_self.size[0]-1, 0].
        :param pos: The (x,y) geometric co-ordinates.
        :returns (int, int): The associated pixel co-ordinates.
        '''
        return (np.int(self.map_size[0]-1-np.floor(pos[1]/self.map_res)), np.int(np.floor(pos[0]/self.map_res)))


    def forward(self, input_map):
        '''
        The callback function.
        :param input_map:
        :param goal: A 2D torch array representing the goal.
        :param start: A 2D torch array representing the start.
        :param cur_index: The current anchor point of patch.
        '''
        enc_output, *_ = self.encoder(input_map)
        seq_logit = self.classPred(enc_output)
        batch_size = input_map.shape[0]
        return rearrange(seq_logit, '(b c) d -> b c d', b=batch_size)
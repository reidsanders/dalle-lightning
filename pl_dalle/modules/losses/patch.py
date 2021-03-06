import torch
import torch.nn as nn
import torch.nn.functional as F
import kornia.augmentation as K


def hinge_d_loss(logits_real, logits_fake):
    loss_real = torch.mean(F.relu(1. - logits_real))
    loss_fake = torch.mean(F.relu(1. + logits_fake))
    d_loss = 0.5 * (loss_real + loss_fake)
    return d_loss


def hinge_g_loss(logits_fake):
    return torch.mean(F.relu(1. - logits_fake))


class ResBlock(nn.Module):
    def __init__(self, in_channel, channel):
        super().__init__()

        self.conv = nn.Sequential(
            nn.ReLU(),
            nn.Conv2d(in_channel, channel, 3, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(channel, in_channel, 1),
        )

    def forward(self, input):
        out = self.conv(input)
        out += input

        return out


class PatchDiscriminator(nn.Module):
    def __init__(
        self,
        patch_size,
        in_channel,
        channel,
        n_res_block,
        n_res_channel,
        n_pool_channel=64,
    ):
        super().__init__()
        blocks = [
            K.RandomCrop((patch_size, patch_size), cropping_mode='resample'),
            nn.Conv2d(in_channel, channel, 3, padding=1),
        ]

        for i in range(n_res_block):
            blocks.append(ResBlock(channel, n_res_channel))

        blocks.extend([
            nn.ReLU(inplace=True),
            nn.Conv2d(channel, n_pool_channel, 1),
            nn.AvgPool2d(patch_size // 4),
            nn.Flatten(),
            nn.Linear(n_pool_channel * 4 * 4, n_pool_channel),
            nn.ReLU(inplace=True),
            nn.Linear(channel, 1)
        ])
        self.blocks = nn.Sequential(*blocks)

        for module in self.modules():
            if isinstance(module, (nn.Conv2d, nn.Linear)):
                module = nn.utils.spectral_norm(module)

    def forward(self, input):
        return self.blocks(input)

    def d_loss(self, reals, fakes):
        real_preds = self.forward(reals)
        fake_preds = self.forward(fakes)

        return hinge_d_loss(real_preds, fake_preds)

    def g_loss(self, fakes):
        return hinge_g_loss(self.forward(fakes))


class PatchReconstructionDiscriminator(PatchDiscriminator):
    def __init__(
        self,
        patch_size,
        in_channel,
        channel,
        n_res_block,
        n_res_channel,
    ):
        super().__init__(
            patch_size,
            in_channel * 2,
            channel,
            n_res_block,
            n_res_channel,
        )
        self.patch_size = patch_size
        self.in_channel = in_channel

    def forward(self, x, y):
        assert x.shape == y.shape
        input = torch.stack([x, y], dim=1)
        return super().forward(input)

    def d_loss(self, reals, fakes):
        assert reals.shape == fakes.shape
        reals_1, reals_2 = reals.reshape(2, -1, self.in_channel, self.patch_size, self.patch_size)
        fakes_1, fakes_2 = fakes.reshape(2, -1, self.in_channel, self.patch_size, self.patch_size)
        logits_real = self.forward(reals_1, fakes_1)
        logits_fake = self.forward(fakes_1, reals_1)
        return hinge_d_loss(logits_real, logits_fake)

    def g_loss(self, reals, fakes):
        assert reals.shape == fakes.shape
        reals_1, reals_2 = reals.reshape(2, -1, self.in_channel, self.patch_size, self.patch_size)
        fakes_1, fakes_2 = fakes.reshape(2, -1, self.in_channel, self.patch_size, self.patch_size)
        logits_real = self.forward(reals_1, fakes_1)
        logits_fake = self.forward(fakes_1, reals_1)
        return hinge_d_loss(logits_fake, logits_real)
